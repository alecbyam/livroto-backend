from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import uuid
import math

from app.database import get_db
from app.dependencies import get_current_user, get_current_tenant
from app.core.rbac import Role, ROLE_HIERARCHY, role_level, require_min_role
from app.core.exceptions import NotFoundError, ForbiddenError
from app.modules.location.models import LocationTracking
from app.modules.orders.models import Order

router = APIRouter()


class PositionUpdate(BaseModel):
    latitude: float
    longitude: float
    accuracy: float | None = None
    speed_kmh: float | None = None
    order_id: uuid.UUID | None = None


@router.post("/update", status_code=201)
async def update_position(
    body: PositionUpdate,
    tenant=Depends(get_current_tenant),
    current_user=Depends(require_min_role(Role.RIDER)),
    db: AsyncSession = Depends(get_db),
):
    """
    Le livreur (rider) envoie sa position GPS toutes les N secondes.
    Côté app mobile (Flutter), appeler toutes les 10-30s selon le réseau.
    """
    if not (-90 <= body.latitude <= 90) or not (-180 <= body.longitude <= 180):
        from app.core.exceptions import ValidationError
        raise ValidationError("Coordonnées GPS invalides")

    if body.order_id:
        # Un livreur ne peut pousser une position rattachée qu'à une commande qui lui est assignée.
        order_result = await db.execute(
            select(Order).where(Order.id == body.order_id, Order.tenant_id == tenant.id)
        )
        order = order_result.scalar_one_or_none()
        if not order or order.rider_id != current_user.id:
            raise ForbiddenError("Cette commande ne t'est pas assignée")

    loc = LocationTracking(
        tenant_id=tenant.id,
        user_id=current_user.id,
        order_id=body.order_id,
        latitude=body.latitude,
        longitude=body.longitude,
        accuracy=body.accuracy,
        speed_kmh=body.speed_kmh,
    )
    db.add(loc)
    return {"recorded": True}


@router.get("/rider/{rider_id}/current")
async def get_rider_current_position(
    rider_id: uuid.UUID,
    tenant=Depends(get_current_tenant),
    current_user=Depends(require_min_role(Role.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Dernière position connue d'un livreur (dispatch/audit — réservé aux managers+)."""
    result = await db.execute(
        select(LocationTracking)
        .where(
            LocationTracking.tenant_id == tenant.id,
            LocationTracking.user_id == rider_id,
        )
        .order_by(LocationTracking.recorded_at.desc())
        .limit(1)
    )
    loc = result.scalar_one_or_none()
    if not loc:
        raise NotFoundError("Position livreur")

    return {
        "rider_id": str(rider_id),
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "accuracy": loc.accuracy,
        "speed_kmh": loc.speed_kmh,
        "recorded_at": loc.recorded_at.isoformat(),
    }


@router.get("/order/{order_id}/track")
async def track_order(
    order_id: uuid.UUID,
    tenant=Depends(get_current_tenant),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Suivi d'une commande en temps réel.
    Retourne la position du livreur + distance estimée jusqu'au client.
    """
    order_result = await db.execute(
        select(Order).where(Order.id == order_id, Order.tenant_id == tenant.id)
    )
    order = order_result.scalar_one_or_none()
    if not order:
        raise NotFoundError("Commande")

    # Seuls le client de la commande, le livreur assigné, ou un manager+ peuvent la suivre.
    is_party = current_user.id in (order.customer_id, order.rider_id)
    if not is_party and role_level(current_user.role) < ROLE_HIERARCHY[Role.MANAGER]:
        raise ForbiddenError("Tu n'as pas accès au suivi de cette commande")

    if not order.rider_id:
        return {"status": "no_rider_assigned", "tracking": None}

    result = await db.execute(
        select(LocationTracking)
        .where(
            LocationTracking.tenant_id == tenant.id,
            LocationTracking.user_id == order.rider_id,
        )
        .order_by(LocationTracking.recorded_at.desc())
        .limit(1)
    )
    loc = result.scalar_one_or_none()

    if not loc:
        return {"status": "pending", "tracking": None}

    distance_km = None
    if order.delivery_lat and order.delivery_lng:
        distance_km = _haversine(
            loc.latitude, loc.longitude,
            float(order.delivery_lat), float(order.delivery_lng),
        )

    return {
        "status": "tracking",
        "order_status": order.status,
        "rider": {
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "speed_kmh": loc.speed_kmh,
            "last_update": loc.recorded_at.isoformat(),
        },
        "destination": {
            "latitude": float(order.delivery_lat) if order.delivery_lat else None,
            "longitude": float(order.delivery_lng) if order.delivery_lng else None,
            "address": order.delivery_address,
        },
        "distance_km": round(distance_km, 2) if distance_km else None,
        "eta_minutes": _estimate_eta(distance_km, loc.speed_kmh) if distance_km else None,
    }


@router.get("/rider/{rider_id}/history")
async def rider_location_history(
    rider_id: uuid.UUID,
    limit: int = Query(50, le=200),
    order_id: uuid.UUID | None = None,
    tenant=Depends(get_current_tenant),
    current_user=Depends(require_min_role(Role.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Historique de positions d'un livreur (utile pour les audits)."""
    query = select(LocationTracking).where(
        LocationTracking.tenant_id == tenant.id,
        LocationTracking.user_id == rider_id,
    )
    if order_id:
        query = query.where(LocationTracking.order_id == order_id)

    query = query.order_by(LocationTracking.recorded_at.desc()).limit(limit)
    result = await db.execute(query)
    locs = result.scalars().all()

    return [
        {
            "lat": l.latitude,
            "lng": l.longitude,
            "speed": l.speed_kmh,
            "at": l.recorded_at.isoformat(),
        }
        for l in locs
    ]


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance en km entre deux points GPS (formule Haversine)."""
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _estimate_eta(distance_km: float, speed_kmh: float | None) -> int:
    """Estimation du temps d'arrivée en minutes."""
    speed = speed_kmh if speed_kmh and speed_kmh > 5 else 25  # vitesse par défaut en ville
    return max(1, round((distance_km / speed) * 60))

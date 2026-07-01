from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from decimal import Decimal
import uuid

from app.database import get_db
from app.dependencies import get_current_user, get_current_tenant
from app.core.rbac import Role, require_min_role
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.orders.models import Order, OrderItem, OrderStatus
from app.modules.products.models import Product
from pydantic import BaseModel

router = APIRouter()


class OrderItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int


class OrderCreate(BaseModel):
    items: list[OrderItemIn]
    delivery_address: str | None = None
    delivery_lat: float | None = None
    delivery_lng: float | None = None
    notes: str | None = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    rider_id: uuid.UUID | None = None


@router.post("/", status_code=201)
async def create_order(
    body: OrderCreate,
    background_tasks: BackgroundTasks,
    tenant=Depends(get_current_tenant),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.items:
        raise ValidationError("La commande doit contenir au moins un article")

    total = Decimal("0")
    order_items = []

    for item_in in body.items:
        result = await db.execute(
            select(Product).where(
                Product.id == item_in.product_id,
                Product.tenant_id == tenant.id,
                Product.is_active == True,
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise NotFoundError(f"Produit {item_in.product_id}")
        if product.stock_qty < item_in.quantity:
            raise ValidationError(f"Stock insuffisant pour '{product.name}' (dispo: {product.stock_qty})")

        unit_price = product.price_promo or product.price
        subtotal = unit_price * item_in.quantity
        total += subtotal

        order_items.append(OrderItem(
            product_id=product.id,
            quantity=item_in.quantity,
            unit_price=unit_price,
            subtotal=subtotal,
        ))
        # Déduire du stock
        product.stock_qty -= item_in.quantity

    order = Order(
        tenant_id=tenant.id,
        customer_id=current_user.id,
        total_amount=total,
        delivery_address=body.delivery_address,
        delivery_lat=body.delivery_lat,
        delivery_lng=body.delivery_lng,
        notes=body.notes,
        items=order_items,
    )
    db.add(order)
    await db.flush()

    # Notification WhatsApp confirmation
    background_tasks.add_task(
        _notify_order_created,
        phone=current_user.phone,
        order_id=str(order.id),
        total=float(total),
    )

    return {"id": str(order.id), "total": float(total), "status": order.status}


async def _notify_order_created(phone: str | None, order_id: str, total: float):
    if not phone:
        return
    from app.modules.notifications.whatsapp import whatsapp_client
    await whatsapp_client.send_text(
        phone.replace("+", ""),
        f"✅ Commande #{order_id[:8]} confirmée !\n"
        f"Total : {total:.2f} USD\n"
        f"Nous vous notifions dès qu'elle est en route.",
    )


@router.get("/")
async def list_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    status: OrderStatus | None = None,
    tenant=Depends(get_current_tenant),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.rbac import role_level, ROLE_HIERARCHY
    query = select(Order).options(selectinload(Order.items)).where(
        Order.tenant_id == tenant.id
    )
    # Les customers ne voient que leurs propres commandes
    if role_level(current_user.role) < ROLE_HIERARCHY[Role.MANAGER]:
        query = query.where(Order.customer_id == current_user.id)
    if status:
        query = query.where(Order.status == status)

    query = query.order_by(Order.created_at.desc()).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    orders = result.scalars().all()

    return [
        {
            "id": str(o.id),
            "status": o.status,
            "total_amount": float(o.total_amount),
            "currency": o.currency,
            "created_at": o.created_at.isoformat(),
            "items_count": len(o.items),
        }
        for o in orders
    ]


@router.get("/{order_id}")
async def get_order(
    order_id: uuid.UUID,
    tenant=Depends(get_current_tenant),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id, Order.tenant_id == tenant.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise NotFoundError("Commande")

    from app.core.rbac import role_level, ROLE_HIERARCHY
    if role_level(current_user.role) < ROLE_HIERARCHY[Role.MANAGER]:
        if str(order.customer_id) != str(current_user.id):
            raise NotFoundError("Commande")

    return {
        "id": str(order.id),
        "status": order.status,
        "total_amount": float(order.total_amount),
        "currency": order.currency,
        "delivery_address": order.delivery_address,
        "notes": order.notes,
        "created_at": order.created_at.isoformat(),
        "items": [
            {
                "product_id": str(i.product_id),
                "quantity": i.quantity,
                "unit_price": float(i.unit_price),
                "subtotal": float(i.subtotal),
            }
            for i in order.items
        ],
    }


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: uuid.UUID,
    body: OrderStatusUpdate,
    background_tasks: BackgroundTasks,
    tenant=Depends(get_current_tenant),
    current_user=Depends(require_min_role(Role.RIDER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.tenant_id == tenant.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise NotFoundError("Commande")

    order.status = body.status
    if body.rider_id:
        order.rider_id = body.rider_id

    # Notification client sur changement de statut
    from sqlalchemy import select as sel
    from app.modules.users.models import User
    cust = await db.execute(sel(User).where(User.id == order.customer_id))
    customer = cust.scalar_one_or_none()
    if customer and customer.phone:
        background_tasks.add_task(
            _notify_status_change,
            phone=customer.phone,
            order_id=str(order.id),
            status=body.status.value,
        )

    return {"id": str(order.id), "status": order.status}


async def _notify_status_change(phone: str, order_id: str, status: str):
    from app.modules.notifications.whatsapp import whatsapp_client
    await whatsapp_client.send_order_status(phone.replace("+", ""), order_id, status)

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
import uuid

from app.database import get_db
from app.dependencies import get_current_user, get_current_tenant
from app.core.rbac import Role, require_min_role
from app.core.exceptions import NotFoundError, ConflictError
from app.core.security import hash_password
from app.modules.users.models import User

router = APIRouter()


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class UserAdminUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None


@router.get("/")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    role: str | None = None,
    search: str | None = None,
    tenant=Depends(get_current_tenant),
    current_user=Depends(require_min_role(Role.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).where(User.tenant_id == tenant.id)
    if role:
        query = query.where(User.role == role)
    if search:
        query = query.where(
            User.full_name.ilike(f"%{search}%") | User.email.ilike(f"%{search}%")
        )
    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "phone": u.phone,
            "role": u.role,
            "is_active": u.is_active,
            "is_verified": u.is_verified,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.get("/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    tenant=Depends(get_current_tenant),
    current_user=Depends(require_min_role(Role.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("Utilisateur")
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role,
        "is_active": user.is_active,
    }


@router.put("/me")
async def update_profile(
    body: UserUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    return {"message": "Profil mis à jour"}


@router.patch("/{user_id}/admin")
async def admin_update_user(
    user_id: uuid.UUID,
    body: UserAdminUpdate,
    tenant=Depends(get_current_tenant),
    current_user=Depends(require_min_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("Utilisateur")

    if body.role:
        valid_roles = [r.value for r in Role]
        if body.role not in valid_roles:
            from app.core.exceptions import ValidationError
            raise ValidationError(f"Rôle invalide. Valeurs possibles : {valid_roles}")
        user.role = body.role

    if body.is_active is not None:
        user.is_active = body.is_active

    return {"id": str(user.id), "role": user.role, "is_active": user.is_active}

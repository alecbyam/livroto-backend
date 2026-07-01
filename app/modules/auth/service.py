from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp,
)
from app.core.exceptions import AuthError, ConflictError, NotFoundError
from app.config import settings
from app.modules.users.models import User, RefreshToken
from app.modules.tenants.models import Tenant


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str,
    tenant_slug: str,
    phone: str | None = None,
    role: str = "customer",
) -> User:
    # Vérifie que le tenant existe
    result = await db.execute(
        select(Tenant).where(Tenant.slug == tenant_slug, Tenant.is_active == True)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise NotFoundError("Tenant")

    # Vérifie que l'email n'existe pas déjà
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ConflictError("Un compte avec cet email existe déjà")

    user = User(
        tenant_id=tenant.id,
        email=email,
        phone=phone,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


async def login_user(db: AsyncSession, email: str, password: str) -> dict:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        raise AuthError("Email ou mot de passe incorrect")

    if not user.is_active:
        raise AuthError("Compte désactivé — contactez l'administrateur")

    # Mise à jour du last_login
    user.last_login = datetime.now(timezone.utc)

    token_data = {"sub": str(user.id), "tenant": str(user.tenant_id), "role": user.role}
    access_token = create_access_token(token_data)
    refresh_token_value = create_refresh_token(token_data)

    rt = RefreshToken(
        user_id=user.id,
        token=refresh_token_value,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(rt)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token_value,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> dict:
    try:
        payload = decode_token(refresh_token)
    except ValueError:
        raise AuthError("Refresh token invalide")

    if payload.get("type") != "refresh":
        raise AuthError("Token de mauvais type")

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == refresh_token,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    rt = result.scalar_one_or_none()
    if not rt:
        raise AuthError("Refresh token expiré ou révoqué")

    # Rotation : invalide l'ancien et crée un nouveau
    rt.revoked = True

    user_id = payload["sub"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise AuthError("Utilisateur introuvable ou inactif")

    token_data = {"sub": str(user.id), "tenant": str(user.tenant_id), "role": user.role}
    new_access = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)

    new_rt = RefreshToken(
        user_id=user.id,
        token=new_refresh,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_rt)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


async def logout_user(db: AsyncSession, refresh_token: str) -> None:
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == refresh_token)
    )
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked = True

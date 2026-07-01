from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.security import decode_token
from app.core.exceptions import AuthError, TenantError

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.users.models import User

    if not credentials:
        raise AuthError("Token d'authentification manquant")

    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise AuthError("Token invalide ou expiré")

    if payload.get("type") != "access":
        raise AuthError("Type de token incorrect")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("Token sans identifiant utilisateur")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise AuthError("Utilisateur introuvable")
    if not user.is_active:
        raise AuthError("Compte désactivé")

    return user


async def get_current_tenant(
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.tenants.models import Tenant

    tenant_id = request.headers.get("X-Tenant-ID") or str(current_user.tenant_id)

    if not tenant_id:
        raise TenantError("X-Tenant-ID manquant")

    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active == True)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise TenantError("Tenant introuvable ou inactif")

    if str(current_user.tenant_id) != str(tenant.id):
        from app.core.rbac import Role, role_level, ROLE_HIERARCHY
        if role_level(current_user.role) < ROLE_HIERARCHY[Role.SUPER_ADMIN]:
            raise TenantError("Accès à ce tenant non autorisé")

    return tenant

from enum import Enum
from functools import wraps
from fastapi import Depends
from app.core.exceptions import ForbiddenError


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"   # Accès à tous les tenants
    ADMIN = "admin"               # Accès complet sur son tenant
    MANAGER = "manager"           # Gestion stock, commandes, rapports
    VENDOR = "vendor"             # Gestion de ses produits uniquement
    RIDER = "rider"               # Livraisons assignées
    CUSTOMER = "customer"         # Commandes et profil personnel


# Hiérarchie : chaque rôle hérite des droits des rôles en dessous
ROLE_HIERARCHY: dict[Role, int] = {
    Role.SUPER_ADMIN: 100,
    Role.ADMIN: 80,
    Role.MANAGER: 60,
    Role.VENDOR: 40,
    Role.RIDER: 20,
    Role.CUSTOMER: 10,
}


def role_level(role: str) -> int:
    try:
        return ROLE_HIERARCHY[Role(role)]
    except (ValueError, KeyError):
        return 0


def require_role(*roles: Role):
    """Décorateur FastAPI : vérifie que l'utilisateur a l'un des rôles requis."""
    from app.dependencies import get_current_user

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user=Depends(get_current_user), **kwargs):
            user_role = Role(current_user.role)
            allowed_levels = {ROLE_HIERARCHY[r] for r in roles}
            if role_level(current_user.role) not in allowed_levels and \
               role_level(current_user.role) < ROLE_HIERARCHY.get(Role.ADMIN, 80):
                raise ForbiddenError(
                    f"Rôle requis : {[r.value for r in roles]}, "
                    f"rôle actuel : {current_user.role}"
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator


def require_min_role(min_role: Role):
    """Vérifie que le rôle de l'utilisateur est au moins égal à min_role."""
    from app.dependencies import get_current_user

    async def check(current_user=Depends(get_current_user)):
        if role_level(current_user.role) < ROLE_HIERARCHY[min_role]:
            raise ForbiddenError(
                f"Niveau minimum requis : {min_role.value}, "
                f"rôle actuel : {current_user.role}"
            )
        return current_user
    return check

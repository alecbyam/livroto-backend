from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

# Instance partagée : importée par main.py (middleware + handler d'erreur) et
# par les routers qui ont besoin d'une limite plus stricte que la valeur par
# défaut (ex. login/OTP). Un seul Limiter par process — ne pas en recréer un
# ailleurs, sinon les compteurs ne sont plus partagés entre routes.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)

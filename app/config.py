from functools import lru_cache
import secrets
from pydantic_settings import BaseSettings


def _default_secret() -> str:
    """En dev, génère un secret aléatoire. En prod, Railway fournit SECRET_KEY."""
    return secrets.token_hex(32)


class Settings(BaseSettings):
    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "Livroto SaaS"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    BASE_URL: str = "http://localhost:8000"

    # ── Auth ──────────────────────────────────────────────────────────────────
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://localhost/livroto"

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── CORS — stocké comme str, exposé comme list via la propriété ───────────
    # Passer en variable Railway : url1,url2  (séparées par virgule)
    ALLOWED_ORIGINS_STR: str = "http://localhost:3000"

    # ── FlexPay ───────────────────────────────────────────────────────────────
    FLEXPAY_TOKEN: str = ""
    FLEXPAY_MERCHANT: str = ""
    FLEXPAY_BASE_URL: str = "https://backend.flexpay.cd/api/rest/v1"
    FLEXPAY_WEBHOOK_SECRET: str = ""

    # ── Stripe ────────────────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ── WhatsApp ──────────────────────────────────────────────────────────────
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_API_VERSION: str = "v20.0"

    # ── Twilio ────────────────────────────────────────────────────────────────
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # ── Claude API ────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS_STR.split(",") if o.strip()]

    @property
    def DATABASE_URL_ASYNC(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def WHATSAPP_API_URL(self) -> str:
        return f"https://graph.facebook.com/{self.WHATSAPP_API_VERSION}"

    model_config = {"env_file": ".env", "case_sensitive": True}

    @property
    def secret_key_safe(self) -> str:
        """Retourne SECRET_KEY ou lève une erreur claire si vide en prod."""
        if not self.SECRET_KEY:
            if not self.DEBUG:
                raise RuntimeError(
                    "SECRET_KEY est vide — configurez-la dans Railway (Settings → Variables). "
                    "Générez avec : python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            # Dev only : génère un secret éphémère (différent à chaque restart)
            return _default_secret()
        return self.SECRET_KEY


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

from celery import Celery
import redis.asyncio as aioredis
from app.config import settings

# ── Celery ────────────────────────────────────────────────────────────────────
celery_app = Celery(
    "saas_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.notification_tasks",
        "app.tasks.payment_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Kinshasa",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,           # Requeue si le worker crash pendant l'exécution
    worker_prefetch_multiplier=1,  # Traite une tâche à la fois (prudence sur 2G)
    task_routes={
        "app.tasks.payment_tasks.*": {"queue": "payments"},
        "app.tasks.notification_tasks.*": {"queue": "notifications"},
    },
    beat_schedule={
        # Vérifie les paiements FlexPay en attente toutes les 5 min
        "check-pending-flexpay-payments": {
            "task": "app.tasks.payment_tasks.check_pending_flexpay_payments",
            "schedule": 300.0,
        },
        # Alerte stock critique toutes les heures
        "stock-alert": {
            "task": "app.tasks.notification_tasks.send_low_stock_alerts",
            "schedule": 3600.0,
        },
    },
)


# ── Redis async (pour OTP, cache) ─────────────────────────────────────────────
_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if not _redis_pool:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    return _redis_pool


class _RedisProxy:
    """Proxy qui initialise Redis à la première utilisation."""
    async def setex(self, key: str, seconds: int, value: str):
        r = await get_redis()
        await r.setex(key, seconds, value)

    async def get(self, key: str):
        r = await get_redis()
        return await r.get(key)

    async def delete(self, key: str):
        r = await get_redis()
        await r.delete(key)

    async def exists(self, key: str) -> bool:
        r = await get_redis()
        return bool(await r.exists(key))


redis_client = _RedisProxy()

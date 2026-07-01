from app.tasks.celery_app import celery_app
from loguru import logger
import asyncio


def _run(coro):
    """Exécute une coroutine depuis un contexte Celery (synchrone)."""
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(name="app.tasks.notification_tasks.send_whatsapp", bind=True, max_retries=3)
def send_whatsapp(self, phone: str, message: str):
    """Tâche Celery : envoi WhatsApp avec retry automatique."""
    try:
        from app.modules.notifications.whatsapp import whatsapp_client
        result = _run(whatsapp_client.send_text(phone, message))
        if result:
            logger.info(f"[Task] WhatsApp envoyé à {phone}")
        else:
            raise ValueError("Échec envoi WhatsApp")
    except Exception as exc:
        logger.warning(f"[Task] WhatsApp retry {self.request.retries} pour {phone}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(name="app.tasks.notification_tasks.send_sms", bind=True, max_retries=3)
def send_sms(self, phone: str, message: str):
    """Tâche Celery : envoi SMS Twilio avec retry."""
    try:
        from app.modules.notifications.twilio import twilio_client
        ok = _run(twilio_client.send_sms(phone, message))
        if not ok:
            raise ValueError("Échec envoi SMS")
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


@celery_app.task(name="app.tasks.notification_tasks.send_payment_confirmation")
def send_payment_confirmation(phone: str, amount: float, order_id: str):
    from app.modules.notifications.whatsapp import whatsapp_client
    _run(whatsapp_client.send_text(
        phone.replace("+", ""),
        f"💰 Paiement de {amount:.2f} USD confirmé !\n"
        f"Commande #{order_id[:8]} en cours de préparation. Merci !",
    ))


@celery_app.task(name="app.tasks.notification_tasks.send_order_status_update")
def send_order_status_update(phone: str, order_id: str, status: str):
    from app.modules.notifications.whatsapp import whatsapp_client
    _run(whatsapp_client.send_order_status(phone.replace("+", ""), order_id, status))


@celery_app.task(name="app.tasks.notification_tasks.send_low_stock_alerts")
def send_low_stock_alerts():
    """Vérifie les produits en stock critique et notifie les admins."""
    from app.database import AsyncSessionLocal
    from app.modules.products.models import Product
    from sqlalchemy import select

    async def _check():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Product).where(
                    Product.is_active == True,
                    Product.stock_qty <= Product.stock_alert,
                )
            )
            products = result.scalars().all()
            if products:
                names = ", ".join(p.name for p in products[:5])
                logger.warning(f"[Stock Alert] {len(products)} produit(s) en stock critique : {names}")

    _run(_check())


@celery_app.task(name="app.tasks.notification_tasks.broadcast_marketing")
def broadcast_marketing(phones: list[str], message: str, channel: str = "whatsapp"):
    """Envoi marketing en masse via Celery (non-bloquant)."""
    if channel == "whatsapp":
        from app.modules.notifications.whatsapp import whatsapp_client
        results = _run(whatsapp_client.send_marketing_blast(phones, message))
    else:
        from app.modules.notifications.twilio import twilio_client
        results = _run(twilio_client.send_bulk_sms(phones, message))
    logger.info(f"[Broadcast] {results}")
    return results

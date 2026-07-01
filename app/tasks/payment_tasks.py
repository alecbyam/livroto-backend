from app.tasks.celery_app import celery_app
from loguru import logger
import asyncio


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(name="app.tasks.payment_tasks.check_pending_flexpay_payments")
def check_pending_flexpay_payments():
    """
    Vérifie toutes les 5 min les paiements FlexPay en attente.
    FlexPay peut mettre quelques minutes à confirmer un paiement Mobile Money.
    """
    from app.database import AsyncSessionLocal
    from app.modules.payments.models import Payment, PaymentProvider, PaymentStatus
    from app.modules.payments.flexpay import flexpay_client
    from app.modules.orders.models import Order, OrderStatus
    from sqlalchemy import select
    from datetime import datetime, timezone, timedelta

    async def _check():
        async with AsyncSessionLocal() as db:
            # Cherche les paiements FlexPay en attente depuis moins de 2h
            cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
            result = await db.execute(
                select(Payment).where(
                    Payment.provider == PaymentProvider.FLEXPAY,
                    Payment.status == PaymentStatus.PENDING,
                    Payment.created_at >= cutoff,
                    Payment.provider_ref.is_not(None),
                )
            )
            payments = result.scalars().all()
            logger.info(f"[FlexPay check] {len(payments)} paiement(s) en attente")

            for payment in payments:
                try:
                    status_data = await flexpay_client.check_payment_status(payment.provider_ref)
                    if status_data["status"] == "success":
                        payment.status = PaymentStatus.SUCCESS
                        payment.webhook_received_at = datetime.now(timezone.utc)
                        if payment.order_id:
                            order_result = await db.execute(select(Order).where(Order.id == payment.order_id))
                            order = order_result.scalar_one_or_none()
                            if order:
                                order.status = OrderStatus.CONFIRMED
                        logger.info(f"[FlexPay check] paiement {payment.id} confirmé")
                    elif status_data["status"] == "failed":
                        payment.status = PaymentStatus.FAILED
                except Exception as e:
                    logger.error(f"[FlexPay check] erreur pour {payment.provider_ref}: {e}")

            await db.commit()

    _run(_check())

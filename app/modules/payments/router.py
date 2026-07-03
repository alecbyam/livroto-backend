from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import uuid
import stripe

from app.database import get_db
from app.dependencies import get_current_user, get_current_tenant
from app.modules.payments.models import Payment, PaymentProvider, PaymentStatus
from app.modules.payments.flexpay import flexpay_client
from app.modules.payments.stripe_client import stripe_client
from app.modules.orders.models import Order, OrderStatus
from app.core.exceptions import NotFoundError, PaymentError
from loguru import logger

router = APIRouter()


# ── FlexPay ───────────────────────────────────────────────────────────────────

class FlexPayInitiate(BaseModel):
    order_id: uuid.UUID
    phone: str          # 243XXXXXXXXX


@router.post("/flexpay/initiate")
async def initiate_flexpay(
    body: FlexPayInitiate,
    tenant=Depends(get_current_tenant),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == body.order_id, Order.tenant_id == tenant.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise NotFoundError("Commande")

    try:
        fp_result = await flexpay_client.initiate_payment(
            amount=float(order.total_amount),
            currency=order.currency,
            phone=body.phone,
            order_id=str(order.id),
        )
    except ValueError as e:
        raise PaymentError(str(e))

    payment = Payment(
        tenant_id=tenant.id,
        order_id=order.id,
        provider=PaymentProvider.FLEXPAY,
        provider_ref=fp_result["order_number"],
        amount=order.total_amount,
        currency=order.currency,
        phone_number=body.phone,
        metadata_=fp_result,
    )
    db.add(payment)

    return {
        "payment_id": str(payment.id),
        "reference": fp_result["reference"],
        "message": "Paiement Mobile Money initié. Validez sur votre téléphone.",
    }


@router.post("/webhook/flexpay")
async def flexpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    signature = request.headers.get("X-FlexPay-Signature", "")

    if not flexpay_client.verify_webhook_signature(body, signature):
        raise HTTPException(status_code=401, detail="Signature webhook invalide")

    data = await request.json()
    order_number = data.get("orderNumber")
    raw_status = str(data.get("status", ""))
    status_map = {"0": PaymentStatus.SUCCESS, "1": PaymentStatus.PENDING, "2": PaymentStatus.FAILED}
    new_status = status_map.get(raw_status, PaymentStatus.FAILED)

    # Idempotence : un webhook reçu 2x ne doit pas changer le statut 2x
    result = await db.execute(
        select(Payment).where(Payment.provider_ref == order_number)
    )
    payment = result.scalar_one_or_none()

    if payment:
        if payment.status == new_status:
            # Déjà traité — répondre 200 sans rien faire
            logger.info(f"[FlexPay webhook] idempotent skip order_number={order_number}")
            return {"received": True}

        # Vérifier que le paiement appartient bien au tenant concerné (isolation)
        if payment.tenant_id is None:
            logger.error(f"[FlexPay webhook] payment sans tenant_id : {payment.id}")
            return {"received": True}

        payment.status = new_status
        payment.webhook_received_at = datetime.now(timezone.utc)

        if new_status == PaymentStatus.SUCCESS and payment.order_id:
            order_result = await db.execute(
                select(Order).where(
                    Order.id == payment.order_id,
                    Order.tenant_id == payment.tenant_id,  # isolation tenant
                )
            )
            order = order_result.scalar_one_or_none()
            if order and order.status != OrderStatus.CONFIRMED:
                order.status = OrderStatus.CONFIRMED
                background_tasks.add_task(
                    _send_payment_confirmation,
                    phone=payment.phone_number,
                    amount=float(payment.amount),
                    order_id=str(payment.order_id),
                )

    logger.info(f"[FlexPay webhook] order_number={order_number} status={new_status}")
    return {"received": True}


async def _send_payment_confirmation(phone: str | None, amount: float, order_id: str):
    if not phone:
        return
    from app.modules.notifications.whatsapp import whatsapp_client
    await whatsapp_client.send_text(
        phone.replace("+", ""),
        f"💰 Paiement de {amount:.2f} USD confirmé !\n"
        f"Commande #{order_id[:8]} — votre commande est en préparation.\nMerci !",
    )


# ── Stripe ────────────────────────────────────────────────────────────────────

class StripeInitiate(BaseModel):
    order_id: uuid.UUID


@router.post("/stripe/checkout")
async def stripe_checkout(
    body: StripeInitiate,
    tenant=Depends(get_current_tenant),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == body.order_id, Order.tenant_id == tenant.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise NotFoundError("Commande")

    amount_cents = int(order.total_amount * 100)
    session = await stripe_client.create_checkout_session(
        amount_cents=amount_cents,
        currency=order.currency,
        order_id=str(order.id),
        success_url=f"{settings.BASE_URL}/payment/success?order={order.id}",
        cancel_url=f"{settings.BASE_URL}/payment/cancel?order={order.id}",
        customer_email=current_user.email,
    )

    payment = Payment(
        tenant_id=tenant.id,
        order_id=order.id,
        provider=PaymentProvider.STRIPE,
        provider_ref=session["session_id"],
        amount=order.total_amount,
        currency=order.currency,
    )
    db.add(payment)

    return {"checkout_url": session["checkout_url"]}


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe_client.verify_webhook(body, sig)
    except (stripe.SignatureVerificationError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Webhook Stripe invalide : {e}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session["metadata"].get("order_id")

        result = await db.execute(
            select(Payment).where(Payment.provider_ref == session["id"])
        )
        payment = result.scalar_one_or_none()

        if payment:
            if payment.status == PaymentStatus.SUCCESS:
                # Déjà traité (Stripe peut renvoyer le même webhook plusieurs fois) — idempotent.
                logger.info(f"[Stripe webhook] idempotent skip session={session['id']}")
                return {"received": True}

            payment.status = PaymentStatus.SUCCESS
            payment.webhook_received_at = datetime.now(timezone.utc)

            if order_id:
                order_result = await db.execute(
                    select(Order).where(
                        Order.id == order_id,
                        Order.tenant_id == payment.tenant_id,  # isolation tenant
                    )
                )
                order = order_result.scalar_one_or_none()
                if order and order.status != OrderStatus.CONFIRMED:
                    order.status = OrderStatus.CONFIRMED

    logger.info(f"[Stripe webhook] event={event['type']}")
    return {"received": True}


# Import settings pour les URLs
from app.config import settings

"""
Stripe — paiement par carte bancaire, option internationale.
"""
import stripe
from loguru import logger
from app.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeClient:

    async def create_payment_intent(
        self,
        amount_cents: int,      # En centimes : 1000 = 10.00 USD
        currency: str = "usd",
        order_id: str = "",
        customer_email: str = "",
    ) -> dict:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency.lower(),
            metadata={"order_id": order_id, "customer_email": customer_email},
            automatic_payment_methods={"enabled": True},
        )
        logger.info(f"[Stripe] PaymentIntent créé | id={intent.id} | amount={amount_cents} {currency}")
        return {
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id,
            "amount": amount_cents,
            "currency": currency,
        }

    async def create_checkout_session(
        self,
        amount_cents: int,
        currency: str,
        order_id: str,
        success_url: str,
        cancel_url: str,
        customer_email: str | None = None,
    ) -> dict:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": currency.lower(),
                    "unit_amount": amount_cents,
                    "product_data": {"name": f"Commande #{order_id[:8]}"},
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=customer_email,
            metadata={"order_id": order_id},
        )
        return {"session_id": session.id, "checkout_url": session.url}

    def verify_webhook(self, payload: bytes, sig_header: str) -> stripe.Event:
        """Vérifie et décode un webhook Stripe."""
        return stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )


stripe_client = StripeClient()

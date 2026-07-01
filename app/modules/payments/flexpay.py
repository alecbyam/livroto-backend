"""
FlexPay Mobile Money — principal fournisseur de paiement pour la RDC.
Docs : https://flexpay.cd/docs
"""
import hashlib
import hmac
from uuid import uuid4

import httpx
from loguru import logger

from app.config import settings


class FlexPayClient:

    def __init__(self):
        self.base_url = settings.FLEXPAY_BASE_URL
        self.token = settings.FLEXPAY_TOKEN
        self.merchant = settings.FLEXPAY_MERCHANT

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def initiate_payment(
        self,
        amount: float,
        currency: str,
        phone: str,        # Format attendu : 243XXXXXXXXX (sans +)
        order_id: str,
        description: str = "Paiement",
    ) -> dict:
        """
        Lance un paiement Mobile Money FlexPay.
        Retourne la référence interne + la réponse FlexPay brute.
        """
        reference = f"LIV-{uuid4().hex[:10].upper()}"

        payload = {
            "merchant": self.merchant,
            "type": 1,          # 1 = Mobile Money
            "phone": phone.replace("+", "").replace(" ", ""),
            "reference": reference,
            "amount": str(int(amount)),   # FlexPay attend un entier en centimes
            "currency": currency.upper(),
            "description": f"{description} — Réf: {order_id[:8]}",
            "callback": f"{settings.BASE_URL}/api/v1/payments/webhook/flexpay",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/paymentService",
                json=payload,
                headers=self._headers(),
            )
            data = resp.json()

        logger.info(
            f"[FlexPay] initié | ref={reference} | phone={phone} | "
            f"amount={amount} {currency} | code={data.get('code')}"
        )

        if data.get("code") != "0":
            raise ValueError(f"FlexPay erreur : {data.get('message', 'inconnue')}")

        return {
            "reference": reference,
            "order_number": data.get("orderNumber"),
            "provider_response": data,
        }

    async def check_payment_status(self, order_number: str) -> dict:
        """Vérifie le statut d'un paiement FlexPay via son orderNumber."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.base_url}/checkPayment/{order_number}",
                headers=self._headers(),
            )
            data = resp.json()

        status_map = {
            "0": "success",
            "1": "pending",
            "2": "failed",
        }
        return {
            "status": status_map.get(str(data.get("status")), "unknown"),
            "amount": data.get("amount"),
            "phone": data.get("phone"),
            "raw": data,
        }

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Valide la signature HMAC-SHA256 du webhook FlexPay.
        Le header s'appelle X-FlexPay-Signature.
        """
        if not settings.FLEXPAY_WEBHOOK_SECRET:
            logger.warning("[FlexPay] FLEXPAY_WEBHOOK_SECRET non configuré — webhook non validé")
            return False

        expected = hmac.new(
            settings.FLEXPAY_WEBHOOK_SECRET.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


flexpay_client = FlexPayClient()

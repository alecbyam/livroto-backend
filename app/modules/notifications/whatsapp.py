"""
WhatsApp Business API (Meta Graph API).
Canal principal de communication en RDC — 90%+ des utilisateurs l'utilisent.
"""
import httpx
from loguru import logger
from app.config import settings


class WhatsAppClient:

    @property
    def _url(self) -> str:
        return f"{settings.WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        }

    async def send_text(self, to: str, message: str) -> dict | None:
        """
        Envoie un message texte libre.
        `to` : numéro au format international sans +, ex: 243XXXXXXXXX
        """
        if not settings.WHATSAPP_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
            logger.warning("[WhatsApp] Token ou Phone ID non configuré")
            return None

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to.replace("+", "").replace(" ", ""),
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self._url, json=payload, headers=self._headers())
                data = resp.json()
                logger.info(f"[WhatsApp] envoyé à {to} | id={data.get('messages', [{}])[0].get('id')}")
                return data
        except Exception as e:
            logger.error(f"[WhatsApp] erreur envoi à {to}: {e}")
            return None

    async def send_template(
        self,
        to: str,
        template_name: str,
        language: str = "fr",
        params: list[str] | None = None,
    ) -> dict | None:
        """
        Envoie un template pré-approuvé par Meta.
        Obligatoire pour initier une conversation (les messages libres sont
        uniquement autorisés dans les 24h qui suivent un message entrant).
        """
        components = []
        if params:
            components = [{
                "type": "body",
                "parameters": [{"type": "text", "text": str(p)} for p in params],
            }]

        payload = {
            "messaging_product": "whatsapp",
            "to": to.replace("+", "").replace(" ", ""),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self._url, json=payload, headers=self._headers())
                return resp.json()
        except Exception as e:
            logger.error(f"[WhatsApp] erreur template {template_name} à {to}: {e}")
            return None

    async def send_order_status(self, phone: str, order_id: str, status: str) -> None:
        """Notification prête à l'emploi pour le suivi de commande."""
        icons = {
            "confirmed": "✅",
            "preparing": "👨‍🍳",
            "delivering": "🛵",
            "delivered": "📦",
            "cancelled": "❌",
        }
        messages = {
            "confirmed": f"✅ Commande #{order_id[:8]} confirmée ! Nous la préparons.",
            "preparing": f"👨‍🍳 Votre commande #{order_id[:8]} est en préparation.",
            "delivering": f"🛵 Votre commande #{order_id[:8]} est en route vers vous !",
            "delivered": f"📦 Commande #{order_id[:8]} livrée ! Bonne dégustation 😊\nMerci de votre confiance.",
            "cancelled": f"❌ Commande #{order_id[:8]} annulée.\nContactez-nous pour plus d'infos.",
        }
        msg = messages.get(status, f"Commande #{order_id[:8]} — statut : {status}")
        await self.send_text(phone, msg)

    async def send_marketing_blast(self, phones: list[str], message: str) -> dict:
        """Envoi en masse (respecte les limites de débit Meta)."""
        import asyncio
        results = {"sent": 0, "failed": 0}
        for phone in phones:
            result = await self.send_text(phone, message)
            if result:
                results["sent"] += 1
            else:
                results["failed"] += 1
            await asyncio.sleep(0.1)  # 10 msg/s max recommandé par Meta
        return results


whatsapp_client = WhatsAppClient()

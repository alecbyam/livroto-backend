"""
Twilio — SMS et OTP.
Fallback si WhatsApp échoue ou si l'utilisateur n'a pas WhatsApp.
"""
from loguru import logger
from app.config import settings


class TwilioClient:

    def _get_client(self):
        from twilio.rest import Client
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            raise RuntimeError("Twilio non configuré (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN manquants)")
        return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    async def send_otp(self, phone: str, otp: str) -> bool:
        """
        Envoie un OTP par SMS.
        Si Twilio échoue, essaie WhatsApp comme fallback (fréquent en RDC).
        """
        try:
            client = self._get_client()
            message = client.messages.create(
                body=f"Votre code de vérification : {otp}\nValable 10 minutes. Ne partagez pas ce code.",
                from_=settings.TWILIO_FROM_NUMBER,
                to=f"+{phone.replace('+', '')}",
            )
            logger.info(f"[Twilio OTP] envoyé à {phone} | sid={message.sid}")
            return True
        except Exception as e:
            logger.warning(f"[Twilio OTP] échec SMS vers {phone}: {e} — tentative WhatsApp")
            # Fallback WhatsApp
            try:
                from app.modules.notifications.whatsapp import whatsapp_client
                await whatsapp_client.send_text(
                    phone.replace("+", ""),
                    f"🔐 Code de vérification LIVROTO : *{otp}*\nValable 10 minutes.",
                )
                return True
            except Exception as e2:
                logger.error(f"[Fallback WhatsApp OTP] échec : {e2}")
                return False

    async def send_sms(self, phone: str, message: str) -> bool:
        try:
            client = self._get_client()
            msg = client.messages.create(
                body=message,
                from_=settings.TWILIO_FROM_NUMBER,
                to=f"+{phone.replace('+', '')}",
            )
            logger.info(f"[Twilio SMS] envoyé à {phone} | sid={msg.sid}")
            return True
        except Exception as e:
            logger.error(f"[Twilio SMS] erreur : {e}")
            return False

    async def send_bulk_sms(self, phones: list[str], message: str) -> dict:
        import asyncio
        results = {"sent": 0, "failed": 0}
        for phone in phones:
            ok = await self.send_sms(phone, message)
            if ok:
                results["sent"] += 1
            else:
                results["failed"] += 1
            await asyncio.sleep(0.05)
        return results


twilio_client = TwilioClient()

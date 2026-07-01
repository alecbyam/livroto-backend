from fastapi import APIRouter, Depends, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.dependencies import get_current_user, get_current_tenant
from app.core.rbac import Role, require_min_role
from app.config import settings

router = APIRouter()


# ── Webhook WhatsApp (Meta) ───────────────────────────────────────────────────

@router.get("/webhook/whatsapp")
async def whatsapp_verify(
    request: Request,
):
    """Endpoint de vérification du webhook WhatsApp (Meta le contacte une seule fois)."""
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        return int(challenge)

    raise HTTPException(status_code=403, detail="Token de vérification invalide")


@router.post("/webhook/whatsapp")
async def whatsapp_incoming(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Reçoit les messages entrants WhatsApp (réponses clients)."""
    data = await request.json()

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        messages = value.get("messages", [])

        for msg in messages:
            sender = msg["from"]
            if msg["type"] == "text":
                text = msg["text"]["body"]
                background_tasks.add_task(_handle_incoming_whatsapp, sender, text)
    except (KeyError, IndexError):
        pass  # Pas un message entrant (status update, etc.)

    return {"status": "ok"}


async def _handle_incoming_whatsapp(phone: str, text: str):
    """Traite les messages entrants : peut déclencher Claude pour une réponse auto."""
    from app.modules.ai.claude import ai_client
    from app.modules.notifications.whatsapp import whatsapp_client

    text_lower = text.lower().strip()

    # Réponses automatiques simples
    if any(w in text_lower for w in ["bonjour", "salut", "hello", "hallo"]):
        await whatsapp_client.send_text(
            phone,
            "👋 Bonjour ! Bienvenue chez LIVROTO.\n"
            "Tapez :\n• *commande* — suivi de commande\n"
            "• *aide* — assistance\n• *catalogue* — voir les produits",
        )
        return

    # Délègue à Claude pour les questions complexes
    response = await ai_client.customer_support(text, context={"phone": phone})
    await whatsapp_client.send_text(phone, response)


# ── Envoi manuel (admin) ──────────────────────────────────────────────────────

class SendMessageRequest(BaseModel):
    phone: str
    message: str
    channel: str = "whatsapp"  # whatsapp | sms


@router.post("/send")
async def send_notification(
    body: SendMessageRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_min_role(Role.MANAGER)),
):
    if body.channel == "whatsapp":
        from app.modules.notifications.whatsapp import whatsapp_client
        background_tasks.add_task(
            whatsapp_client.send_text,
            body.phone.replace("+", ""),
            body.message,
        )
    elif body.channel == "sms":
        from app.modules.notifications.twilio import twilio_client
        background_tasks.add_task(twilio_client.send_sms, body.phone, body.message)
    else:
        raise HTTPException(status_code=400, detail="Canal invalide (whatsapp | sms)")

    return {"message": f"Notification programmée via {body.channel}", "to": body.phone}


class BroadcastRequest(BaseModel):
    phones: list[str]
    message: str
    channel: str = "whatsapp"


@router.post("/broadcast")
async def broadcast(
    body: BroadcastRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_min_role(Role.ADMIN)),
):
    """Envoi en masse — utiliser avec parcimonie (respect des limites API)."""
    if len(body.phones) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 destinataires par appel")

    if body.channel == "whatsapp":
        from app.modules.notifications.whatsapp import whatsapp_client
        background_tasks.add_task(whatsapp_client.send_marketing_blast, body.phones, body.message)
    else:
        from app.modules.notifications.twilio import twilio_client
        background_tasks.add_task(twilio_client.send_bulk_sms, body.phones, body.message)

    return {"message": f"Broadcast de {len(body.phones)} messages planifié"}

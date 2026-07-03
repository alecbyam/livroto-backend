"""
Claude API (Anthropic) — IA pour support client, marketing, finance, analyse.
"""
import asyncio
import anthropic
from loguru import logger
from app.config import settings

# Timeout global pour tous les appels Claude (réseau 2G RDC)
_CLAUDE_TIMEOUT_S = 15.0


class AIClient:

    def __init__(self):
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        if not self._client:
            if not settings.ANTHROPIC_API_KEY:
                raise RuntimeError("ANTHROPIC_API_KEY non configuré")
            self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    async def _call(self, system: str, user_message: str, max_tokens: int = 1024) -> str:
        """Appel async avec timeout — évite de bloquer le serveur si Claude est lent."""
        loop = asyncio.get_running_loop()
        try:
            message = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self.client.messages.create(
                        model=settings.CLAUDE_MODEL,
                        max_tokens=max_tokens,
                        system=system,
                        messages=[{"role": "user", "content": user_message}],
                    ),
                ),
                timeout=_CLAUDE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[Claude] Timeout après {_CLAUDE_TIMEOUT_S}s")
            raise
        return message.content[0].text

    async def customer_support(self, question: str, context: dict | None = None) -> str:
        """
        Agent support client — répond en français ou swahili selon le message.
        Adapté au contexte RDC : Mobile Money, WhatsApp, PME/ONG.
        """
        system = """Tu es l'assistant IA d'une plateforme de livraison en RDC (Bunia).
Tu réponds en français ou en swahili selon la langue du client.
Tu es chaleureux, direct et concis (max 5 phrases).
Tu connais : FlexPay, Airtel Money, Vodacom M-Pesa, Orange Money.
Si la question dépasse tes capacités, propose de contacter un agent humain via WhatsApp."""

        ctx_text = ""
        if context:
            ctx_text = f"\n\nContexte : {context}"

        try:
            return await self._call(system, question + ctx_text, max_tokens=512)
        except asyncio.TimeoutError:
            return "Je suis momentanément indisponible. Contactez-nous directement sur WhatsApp."
        except Exception as e:
            logger.error(f"[Claude support] erreur : {e}")
            return "Je suis momentanément indisponible. Contactez-nous directement sur WhatsApp."

    async def generate_marketing_message(
        self,
        product_name: str,
        price: float,
        currency: str = "USD",
        promotion: str | None = None,
    ) -> str:
        """Génère un message marketing court pour WhatsApp."""
        prompt = f"""Génère un message WhatsApp marketing percutant pour :
Produit : {product_name}
Prix : {price} {currency}
Promotion : {promotion or "aucune"}

Règles : max 3 lignes, émojis, ton chaleureux et africain, appel à l'action clair.
Public : PME et particuliers à Bunia, RDC."""

        try:
            return await self._call("Tu es un expert en marketing digital africain.", prompt, max_tokens=200)
        except (asyncio.TimeoutError, Exception) as e:
            logger.error(f"[Claude marketing] erreur : {e}")
            return f"🔥 {product_name} disponible à {price} {currency} ! Commandez maintenant."

    async def analyze_sales(self, sales_data: list[dict]) -> str:
        """Analyse des ventes pour le tableau de bord admin."""
        prompt = f"""Analyse ces données de ventes et fournis :
1. Top 3 tendances (bullet points)
2. Produits les plus performants
3. 3 recommandations concrètes pour augmenter les ventes
4. Alertes critiques (stock, chiffre d'affaires)

Données : {sales_data}

Réponds en français, max 300 mots, contexte PME en RDC."""

        try:
            return await self._call(
                "Tu es un analyste financier spécialisé dans les PME africaines.",
                prompt,
                max_tokens=600,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.error(f"[Claude analytics] erreur : {e}")
            return "Analyse temporairement indisponible."

    async def generate_financial_report(self, data: dict) -> str:
        """Génère un rapport financier mensuel automatique."""
        prompt = f"""Génère un rapport financier mensuel pour une PME en RDC :

Données :
- Chiffre d'affaires : {data.get('revenue', 0)} USD
- Commandes : {data.get('orders_count', 0)}
- Nouveau clients : {data.get('new_customers', 0)}
- Panier moyen : {data.get('avg_basket', 0)} USD
- Top produits : {data.get('top_products', [])}

Format : résumé exécutif (3 paragraphes), points clés, recommandations.
Adapté à un gérant de PME à Bunia, RDC."""

        try:
            return await self._call(
                "Tu es un consultant financier pour PME africaines.",
                prompt,
                max_tokens=800,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.error(f"[Claude finance] erreur : {e}")
            return "Rapport financier temporairement indisponible."

    async def classify_support_ticket(self, message: str) -> dict:
        """Classifie un message entrant : catégorie + urgence + langue."""
        prompt = f"""Analyse ce message client et réponds UNIQUEMENT en JSON valide :
Message : "{message}"

Format attendu :
{{"category": "paiement|livraison|produit|compte|autre", "urgency": "high|medium|low", "language": "fr|sw|other", "summary": "résumé en 10 mots max"}}"""

        try:
            import json
            raw = await self._call("Tu es un classificateur de tickets support.", prompt, max_tokens=150)
            raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(raw)
        except (asyncio.TimeoutError, Exception):
            return {"category": "autre", "urgency": "medium", "language": "fr", "summary": message[:50]}


ai_client = AIClient()

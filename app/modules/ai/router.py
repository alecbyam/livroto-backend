from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.dependencies import get_current_user, get_current_tenant
from app.core.rbac import Role, require_min_role
from app.modules.ai.claude import ai_client

router = APIRouter()


class SupportRequest(BaseModel):
    question: str
    context: dict | None = None


class MarketingRequest(BaseModel):
    product_name: str
    price: float
    currency: str = "USD"
    promotion: str | None = None


class SalesAnalysisRequest(BaseModel):
    sales_data: list[dict]


class FinancialReportRequest(BaseModel):
    revenue: float
    orders_count: int
    new_customers: int
    avg_basket: float
    top_products: list[str] = []


@router.post("/support")
async def ai_support(
    body: SupportRequest,
    current_user=Depends(get_current_user),
):
    """Support client IA — répond en français ou swahili."""
    response = await ai_client.customer_support(body.question, body.context)
    return {"response": response}


@router.post("/marketing/generate")
async def generate_marketing(
    body: MarketingRequest,
    current_user=Depends(require_min_role(Role.MANAGER)),
):
    """Génère un message marketing WhatsApp prêt à envoyer."""
    message = await ai_client.generate_marketing_message(
        product_name=body.product_name,
        price=body.price,
        currency=body.currency,
        promotion=body.promotion,
    )
    return {"message": message, "channel": "whatsapp", "ready_to_send": True}


@router.post("/analytics/sales")
async def analyze_sales(
    body: SalesAnalysisRequest,
    current_user=Depends(require_min_role(Role.MANAGER)),
):
    """Analyse IA des données de ventes."""
    analysis = await ai_client.analyze_sales(body.sales_data)
    return {"analysis": analysis}


@router.post("/finance/report")
async def financial_report(
    body: FinancialReportRequest,
    current_user=Depends(require_min_role(Role.ADMIN)),
):
    """Rapport financier mensuel généré par IA."""
    report = await ai_client.generate_financial_report(body.model_dump())
    return {"report": report}


@router.post("/support/classify")
async def classify_ticket(
    body: SupportRequest,
    current_user=Depends(require_min_role(Role.MANAGER)),
):
    """Classifie un message entrant : catégorie, urgence, langue."""
    result = await ai_client.classify_support_ticket(body.question)
    return result

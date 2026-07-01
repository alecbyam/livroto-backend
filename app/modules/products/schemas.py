from decimal import Decimal
from pydantic import BaseModel, field_validator
import uuid


class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    price: Decimal
    price_promo: Decimal | None = None
    currency: str = "USD"
    stock_qty: int = 0
    stock_alert: int = 5
    sku: str | None = None
    category_id: uuid.UUID | None = None
    images: list[str] = []

    @field_validator("price", "price_promo")
    @classmethod
    def price_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Le prix doit être positif")
        return v


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = None
    price_promo: Decimal | None = None
    stock_qty: int | None = None
    is_active: bool | None = None


class ProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    price: Decimal
    price_promo: Decimal | None
    currency: str
    stock_qty: int
    is_active: bool
    images: list[str]

    model_config = {"from_attributes": True}

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, DateTime, ForeignKey, Numeric, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base
import enum


class PaymentProvider(str, enum.Enum):
    FLEXPAY = "flexpay"
    STRIPE = "stripe"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"
    EXPIRED = "expired"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), index=True)
    provider: Mapped[PaymentProvider] = mapped_column(SAEnum(PaymentProvider), nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(255), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[PaymentStatus] = mapped_column(SAEnum(PaymentStatus), default=PaymentStatus.PENDING)
    phone_number: Mapped[str | None] = mapped_column(String(30))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    webhook_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

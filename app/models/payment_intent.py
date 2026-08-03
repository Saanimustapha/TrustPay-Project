# app/models/payment_intent.py
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.enums import PaymentIntentStatus


class PaymentIntent(Base):
    __tablename__ = "payment_intents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=PaymentIntentStatus.REQUIRES_CONFIRMATION, index=True
    )
    client_secret: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    last_payment_error: Mapped[str | None] = mapped_column(Text)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
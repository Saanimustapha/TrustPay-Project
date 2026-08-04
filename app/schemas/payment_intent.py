from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import PaymentIntentPurpose, PaymentIntentStatus


class PaymentIntentCreate(BaseModel):
    amount: Decimal = Field(..., gt=0, max_digits=18, decimal_places=4)
    currency: str = Field(..., min_length=3, max_length=3)
    purpose: PaymentIntentPurpose
    fee_amount: Decimal = Field(default=Decimal("0.0000"), ge=0, max_digits=18, decimal_places=4)
    destination_wallet_id: UUID | None = None
    idempotency_key: str | None = Field(None, max_length=128)
    description: str | None = Field(None, max_length=512)
    metadata: dict | None = None


class PaymentIntentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount: Decimal
    currency: str
    fee_amount: Decimal
    purpose: PaymentIntentPurpose
    status: PaymentIntentStatus
    client_secret: str
    destination_wallet_id: UUID | None
    description: str | None
    metadata: dict | None = Field(None, validation_alias="metadata_")
    reference_id: UUID | None
    last_payment_error: str | None
    created_at: datetime
    updated_at: datetime
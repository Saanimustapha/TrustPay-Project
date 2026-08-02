from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DepositRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, max_digits=18, decimal_places=4)
    currency: str = "GHS"
    idempotency_key: str | None = Field(None, max_length=128)
    description: str | None = Field(None, max_length=512)

    @field_validator("amount")
    @classmethod
    def amount_must_have_at_most_4_decimals(cls, v: Decimal) -> Decimal:
        if v.as_tuple().exponent < -4:
            raise ValueError("Amount supports at most 4 decimal places")
        return v


class TransferRequest(BaseModel):
    to_wallet_id: UUID
    amount: Decimal = Field(..., gt=0, max_digits=18, decimal_places=4)
    currency: str = "GHS"
    idempotency_key: str | None = Field(None, max_length=128)
    description: str | None = Field(None, max_length=512)


class BalanceResponse(BaseModel):
    wallet_id: UUID
    currency: str
    balance: Decimal
    version: int


class TransactionResponse(BaseModel):
    reference_id: UUID
    status: str = "completed"
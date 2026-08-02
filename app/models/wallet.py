import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Currency
from app.db.base import Base

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.ledger import LedgerEntry


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default=Currency.GHS, nullable=False)
    # Never store mutable balance as source of truth.
    # Balance is derived from ledger. We keep a cached balance for speed.
    cached_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=4), default=Decimal("0.0000"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # optimistic locking
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    user: Mapped[User] = relationship("User", back_populates="wallets")
    ledger_entries: Mapped[list[LedgerEntry]] = relationship(
        "LedgerEntry", back_populates="wallet", lazy="noload"  # never load by default
    )
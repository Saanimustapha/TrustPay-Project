# app/models/wallet.py
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    # Never store mutable balance as source of truth.
    # Balance is derived from ledger. We keep a cached balance for speed.
    cached_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=4), default=Decimal("0.0000")
    )
    version: Mapped[int] = mapped_column(default=0)  # optimistic locking
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="wallets")
    ledger_entries = relationship("LedgerEntry", back_populates="wallet")
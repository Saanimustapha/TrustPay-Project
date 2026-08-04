import structlog
logger = structlog.get_logger()

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LedgerEntryType, SystemAccountType
from app.core.exceptions import (
    ConcurrentModificationError,
    InsufficientFundsError,
    UnbalancedTransactionError,
    WalletNotFoundError,
)
from app.models.ledger import LedgerEntry
from app.models.wallet import Wallet
from app.services.system_accounts import SystemAccountService


class LedgerService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.system = SystemAccountService(db)

    async def get_wallet(self, wallet_id: UUID, *, for_update: bool = False) -> Wallet:
        stmt = select(Wallet).where(Wallet.id == wallet_id)
        if for_update:
            stmt = stmt.with_for_update()  # only used in rare strong-consistency paths
        result = await self.db.execute(stmt)
        wallet = result.scalar_one_or_none()
        if wallet is None:
            raise WalletNotFoundError()
        return wallet

    async def get_wallet_for_user(
        self, user_id: UUID, currency: str = "GHS"
    ) -> Wallet:
        result = await self.db.execute(
            select(Wallet).where(
                Wallet.user_id == user_id,
                Wallet.currency == currency,
            )
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            raise WalletNotFoundError()
        return wallet

    async def recompute_balance(self, wallet_id: UUID) -> Decimal:
        """Audit / verification path – sums the immutable ledger."""
        result = await self.db.execute(
            select(LedgerEntry.amount).where(LedgerEntry.wallet_id == wallet_id)
        )
        amounts = result.scalars().all()
        return sum(amounts, Decimal("0.0000"))

    async def _apply_entries(
        self,
        entries: list[dict],
        *,
        idempotency_key: str | None = None,
    ) -> UUID:
        """
        Low-level primitive.
        `entries` = list of {"wallet_id", "amount", "currency", "entry_type", "description"}
        Amounts MUST sum to zero.
        """
        if not entries:
            raise ValueError("No entries provided")

        total = sum((e["amount"] for e in entries), Decimal("0"))
        if total != 0:
            raise UnbalancedTransactionError(f"Entries sum to {total}, expected 0")

        reference_id = uuid4()

        # Idempotency check (fast path)
        if idempotency_key:
            existing = await self.db.execute(
                select(LedgerEntry.reference_id).where(
                    LedgerEntry.idempotency_key == idempotency_key
                )
            )
            existing_ref = existing.scalar_one_or_none()
            if existing_ref is not None:
                logger.info(
                "ledger.idempotency.hit",
                idempotency_key=idempotency_key,
                reference_id=str(existing_ref),
                )
                return existing_ref  # already processed – safe to return

        # Create all ledger entries
        for e in entries:
            entry = LedgerEntry(
                wallet_id=e["wallet_id"],
                amount=e["amount"],
                currency=e["currency"],
                entry_type=e["entry_type"],
                reference_id=reference_id,
                idempotency_key=idempotency_key if e is entries[0] else None,
                description=e.get("description"),
            )
            self.db.add(entry)

        # Update cached balances with optimistic locking
        for e in entries:
            wallet_id = e["wallet_id"]
            amount = e["amount"]

            # Read current version
            result = await self.db.execute(
                select(Wallet.version, Wallet.cached_balance).where(Wallet.id == wallet_id)
            )
            row = result.one_or_none()
            if row is None:
                raise WalletNotFoundError()
            current_version, current_balance = row

            new_balance = current_balance + amount
            if new_balance < 0:
                logger.warning(
                "ledger.insufficient_funds",
                wallet_id=str(wallet_id),
                requested=str(amount),
                available=str(current_balance),
                )
                raise InsufficientFundsError()

            # Optimistic update
            stmt = (
                update(Wallet)
                .where(Wallet.id == wallet_id, Wallet.version == current_version)
                .values(
                    cached_balance=new_balance,
                    version=current_version + 1,
                )
            )
            result = await self.db.execute(stmt)
            if result.rowcount != 1:
                logger.warning(
                "ledger.concurrent_modification",
                wallet_id=str(wallet_id),
                )
                raise ConcurrentModificationError()

        await self.db.flush()
        return reference_id

    # ------------------------------------------------------------------
    # Public high-level operations
    # ------------------------------------------------------------------

    async def deposit(
        self,
        *,
        wallet_id: UUID,
        amount: Decimal,
        currency: str = "GHS",
        idempotency_key: str | None = None,
        description: str | None = None,
        fee_amount: Decimal = Decimal("0.0000"),
    ) -> UUID:
        """
        Credit a user wallet.
        In a real system the matching debit would hit a system/external account.
        For Phase 2 we only credit the user (simplified external funding).
        """
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        if fee_amount < 0:
            raise ValueError("Fee cannot be negative")

        clearing_id = await self.system.get_system_wallet_id(
            currency, SystemAccountType.CLEARING
        )
        fees_id = await self.system.get_system_wallet_id(
            currency, SystemAccountType.FEES
        )

        net_amount = amount - fee_amount
        if net_amount < 0:
            raise ValueError("Fee cannot exceed deposit amount")

        entries = [
            {
                "wallet_id": wallet_id,
                "amount": net_amount,  # credit
                "currency": currency,
                "entry_type": LedgerEntryType.DEPOSIT,
                "description": description or "Deposit",
            },
            {  # Clearing is debited (money entered the system)
                "wallet_id": clearing_id,
                "amount": -amount,
                "currency": currency,
                "entry_type": LedgerEntryType.DEPOSIT,
                "description": "External deposit clearing",
            },
        ]
        if fee_amount > 0:
            entries.append({
                "wallet_id": fees_id,
                "amount": fee_amount,
                "currency": currency,
                "entry_type": LedgerEntryType.FEE,
                "description": "Deposit fee",
            })
        reference_id = await self._apply_entries(entries, idempotency_key=idempotency_key)

        logger.info(
        "ledger.transaction.completed",
        operation="deposit",          
        reference_id=str(reference_id),
        wallet_id=str(wallet_id),
        amount=str(amount),
        fee_amount=str(fee_amount),
        currency=currency,
        idempotency_key=idempotency_key,
        )

        return reference_id


    async def withdraw(
        self,
        *,
        wallet_id: UUID,
        amount: Decimal,
        currency: str,
        idempotency_key: str | None = None,
        description: str | None = None,
        fee_amount: Decimal = Decimal("0.0000"),
    ) -> UUID:
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")

        clearing_id = await self.system.get_system_wallet_id(
            currency, SystemAccountType.CLEARING
        )
        fees_id = await self.system.get_system_wallet_id(
            currency, SystemAccountType.FEES
        )

        total_debit = amount + fee_amount

        entries = [
            {  # User is debited full amount + fee
                "wallet_id": wallet_id,
                "amount": -total_debit,
                "currency": currency,
                "entry_type": LedgerEntryType.WITHDRAWAL,
                "description": description or "Withdrawal",
            },
            {  # Clearing is credited (money leaves the system)
                "wallet_id": clearing_id,
                "amount": amount,
                "currency": currency,
                "entry_type": LedgerEntryType.WITHDRAWAL,
                "description": "External withdrawal clearing",
            },
        ]
        if fee_amount > 0:
            entries.append({
                "wallet_id": fees_id,
                "amount": fee_amount,
                "currency": currency,
                "entry_type": LedgerEntryType.FEE,
                "description": "Withdrawal fee",
            })

        reference_id = await self._apply_entries(entries, idempotency_key=idempotency_key)

        logger.info(
        "ledger.transaction.completed",
        operation="withdraw",          
        reference_id=str(reference_id),
        wallet_id=str(wallet_id),
        amount=str(amount),
        fee_amount=str(fee_amount),
        currency=currency,
        idempotency_key=idempotency_key,
        )

        return reference_id


    async def transfer(
        self,
        *,
        from_wallet_id: UUID,
        to_wallet_id: UUID,
        amount: Decimal,
        currency: str = "GHS",
        idempotency_key: str | None = None,
        description: str | None = None,
        fee_amount: Decimal = Decimal("0.0000"),
    ) -> UUID:
        if amount <= 0:
            raise ValueError("Transfer amount must be positive")
        if from_wallet_id == to_wallet_id:
            raise ValueError("Cannot transfer to the same wallet")

        fees_id = await self.system.get_system_wallet_id(currency, SystemAccountType.FEES)

        entries = [
            {
                "wallet_id": from_wallet_id,
                "amount": -(amount + fee_amount),  # debit
                "currency": currency,
                "entry_type": LedgerEntryType.TRANSFER,
                "description": description or "Transfer out",
            },
            {
                "wallet_id": to_wallet_id,
                "amount": amount,  # credit
                "currency": currency,
                "entry_type": LedgerEntryType.TRANSFER,
                "description": description or "Transfer in",
            },
        ]
        if fee_amount > 0:
            entries.append({
                "wallet_id": fees_id,
                "amount": fee_amount,
                "currency": currency,
                "entry_type": LedgerEntryType.FEE,
                "description": "Transfer fee",
            })
            
        reference_id = await self._apply_entries(entries, idempotency_key=idempotency_key)

        logger.info(
        "ledger.transaction.completed",
        operation="transfer",
        reference_id=str(reference_id),
        from_wallet_id=str(from_wallet_id),
        to_wallet_id=str(to_wallet_id),
        amount=str(amount),
        fee_amount=str(fee_amount),
        currency=currency,
        idempotency_key=idempotency_key,
        )

        return reference_id

        

    async def get_balance(self, wallet_id: UUID) -> Decimal:
        wallet = await self.get_wallet(wallet_id)
        return wallet.cached_balance
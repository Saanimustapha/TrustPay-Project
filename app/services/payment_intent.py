import structlog
logger = structlog.get_logger()

import secrets
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PaymentIntentStatus, PaymentIntentPurpose
from app.core.exceptions import (
    ConcurrentModificationError,
    InsufficientFundsError,
    WalletNotFoundError,
    InvalidStateTransitionError
)
from app.models.payment_intent import PaymentIntent
from app.services.ledger import LedgerService



class PaymentIntentService:
    """
    Production state machine for PaymentIntents.

    Allowed transitions (guarded):
    requires_payment_method → requires_confirmation | canceled
    requires_confirmation   → processing | requires_action | canceled | failed
    requires_action         → processing | canceled | failed
    processing              → succeeded | failed | requires_action
    succeeded / failed / canceled → (terminal)
    """

    # Explicit transition map – single source of truth
    _ALLOWED_TRANSITIONS: dict[str, set[str]] = {
        PaymentIntentStatus.REQUIRES_PAYMENT_METHOD: {
            PaymentIntentStatus.REQUIRES_CONFIRMATION,
            PaymentIntentStatus.CANCELED,
        },
        PaymentIntentStatus.REQUIRES_CONFIRMATION: {
            PaymentIntentStatus.PROCESSING,
            PaymentIntentStatus.REQUIRES_ACTION,
            PaymentIntentStatus.CANCELED,
            PaymentIntentStatus.FAILED,
        },
        PaymentIntentStatus.REQUIRES_ACTION: {
            PaymentIntentStatus.PROCESSING,
            PaymentIntentStatus.CANCELED,
            PaymentIntentStatus.FAILED,
        },
        PaymentIntentStatus.PROCESSING: {
            PaymentIntentStatus.SUCCEEDED,
            PaymentIntentStatus.FAILED,
            PaymentIntentStatus.REQUIRES_ACTION,
        },
        # Terminal states have no outbound transitions
        PaymentIntentStatus.SUCCEEDED: set(),
        PaymentIntentStatus.FAILED: set(),
        PaymentIntentStatus.CANCELED: set(),
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ledger = LedgerService(db)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _generate_client_secret(self) -> str:
        return f"pi_{secrets.token_urlsafe(32)}"

    def _assert_transition(self, current: str, target: str) -> None:
        allowed = self._ALLOWED_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise InvalidStateTransitionError(current, target)

    async def _get_for_update(self, pi_id: UUID, user_id: UUID) -> PaymentIntent:
        result = await self.db.execute(
            select(PaymentIntent)
            .where(PaymentIntent.id == pi_id, PaymentIntent.user_id == user_id)
            .with_for_update()
        )
        pi = result.scalar_one_or_none()
        if pi is None:
            raise ValueError("PaymentIntent not found")
        return pi

    async def _transition(
        self,
        pi: PaymentIntent,
        new_status: str,
        *,
        error: str | None = None,
        reference_id: UUID | None = None,
    ) -> PaymentIntent:
        old_status = pi.status
        self._assert_transition(old_status, new_status)

        stmt = (
            update(PaymentIntent)
            .where(
                PaymentIntent.id == pi.id,
                PaymentIntent.version == pi.version,  # optimistic lock
            )
            .values(
                status=new_status,
                version=pi.version + 1,
                last_payment_error=error,
                reference_id=reference_id or pi.reference_id,
            )
            .returning(PaymentIntent)
        )
        result = await self.db.execute(stmt)
        updated = result.scalar_one_or_none()
        if updated is None:
            logger.error(
            "payment_intent.transition.failed",
            payment_intent_id=str(pi.id),
            from_status=old_status,
            attempted_status=new_status,
            purpose=pi.purpose,
            reason="concurrent_modification",
            )
            raise ConcurrentModificationError()

        logger.info(
        "payment_intent.transition.completed",
        payment_intent_id=str(pi.id),
        user_id=str(pi.user_id),
        from_status=old_status,
        to_status=new_status,
        purpose=pi.purpose,
        amount=str(pi.amount),
        currency=pi.currency,
        reference_id=str(reference_id) if reference_id else None,
        )
        return updated

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        purpose: PaymentIntentPurpose,
        fee_amount: Decimal = Decimal("0.0000"),
        destination_wallet_id: UUID | None = None,
        idempotency_key: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
        initial_status: PaymentIntentStatus = PaymentIntentStatus.REQUIRES_CONFIRMATION,
    ) -> PaymentIntent:
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if fee_amount < 0:
            raise ValueError("Fee cannot be negative")
        if purpose == PaymentIntentPurpose.PAYMENT and destination_wallet_id is None:
            raise ValueError("destination_wallet_id is required for purpose=payment")

        # Idempotency
        if idempotency_key:
            existing = await self.db.execute(
                select(PaymentIntent).where(
                    PaymentIntent.idempotency_key == idempotency_key
                )
            )
            pi = existing.scalar_one_or_none()
            if pi:
                return pi

        pi = PaymentIntent(
            user_id=user_id,
            amount=amount,
            currency=currency,
            fee_amount=fee_amount,
            purpose=purpose.value,
            status=initial_status.value,
            client_secret=self._generate_client_secret(),
            idempotency_key=idempotency_key,
            destination_wallet_id=destination_wallet_id,
            description=description,
            metadata_=metadata,
        )
        self.db.add(pi)
        await self.db.flush()
        return pi

    async def confirm(self, pi_id: UUID, user_id: UUID) -> PaymentIntent:
        """
        Move from requires_confirmation → processing and attempt to execute
        the money movement when the flow is synchronous (internal methods).

        For external methods (card, bank, etc.) you would normally only
        transition to processing here and let a webhook call `succeed()` or `fail()`.
        """
        pi = await self._get_for_update(pi_id, user_id)

        if pi.status != PaymentIntentStatus.REQUIRES_CONFIRMATION:
            raise InvalidStateTransitionError(pi.status, PaymentIntentStatus.PROCESSING)

        # Move to processing first (visible to the outside world)
        pi = await self._transition(pi, PaymentIntentStatus.PROCESSING)

        try:
            reference_id = await self._execute_money_movement(pi)
            pi = await self._transition(
                pi,
                PaymentIntentStatus.SUCCEEDED,
                reference_id=reference_id,
            )
        except (InsufficientFundsError, WalletNotFoundError, ValueError) as exc:
            pi = await self._transition(
                pi,
                PaymentIntentStatus.FAILED,
                error=str(exc),
            )
            raise

        return pi

    async def require_action(self, pi_id: UUID, user_id: UUID, error: str | None = None) -> PaymentIntent:
        """Used when 3DS / redirect / additional authentication is needed."""
        pi = await self._get_for_update(pi_id, user_id)
        return await self._transition(
            pi, PaymentIntentStatus.REQUIRES_ACTION, error=error
        )

    async def succeed(
        self,
        pi_id: UUID,
        user_id: UUID | None = None,
        *,
        reference_id: UUID | None = None,
        # When called from a trusted webhook we may skip user_id check
        from_webhook: bool = False,
    ) -> PaymentIntent:
        if from_webhook:
            result = await self.db.execute(
                select(PaymentIntent).where(PaymentIntent.id == pi_id).with_for_update()
            )
            pi = result.scalar_one_or_none()
            if pi is None:
                raise ValueError("PaymentIntent not found")
        else:
            if user_id is None:
                raise ValueError("user_id required when not from webhook")
            pi = await self._get_for_update(pi_id, user_id)

        return await self._transition(
            pi, PaymentIntentStatus.SUCCEEDED, reference_id=reference_id
        )

    async def fail(
        self,
        pi_id: UUID,
        error: str,
        user_id: UUID | None = None,
        from_webhook: bool = False,
    ) -> PaymentIntent:
        if from_webhook:
            result = await self.db.execute(
                select(PaymentIntent).where(PaymentIntent.id == pi_id).with_for_update()
            )
            pi = result.scalar_one_or_none()
            if pi is None:
                raise ValueError("PaymentIntent not found")
        else:
            if user_id is None:
                raise ValueError("user_id required when not from webhook")
            pi = await self._get_for_update(pi_id, user_id)

        return await self._transition(
            pi, PaymentIntentStatus.FAILED, error=error
        )

    async def cancel(self, pi_id: UUID, user_id: UUID) -> PaymentIntent:
        pi = await self._get_for_update(pi_id, user_id)
        return await self._transition(pi, PaymentIntentStatus.CANCELED)

    # ------------------------------------------------------------------
    # Money movement (strategy based on purpose)
    # ------------------------------------------------------------------

    async def _execute_money_movement(self, pi: PaymentIntent) -> UUID:
        """
        Executes the actual ledger entries according to the purpose.
        This is the single place that talks to the LedgerService.
        """
        purpose = PaymentIntentPurpose(pi.purpose)

        if purpose == PaymentIntentPurpose.DEPOSIT:
            wallet = await self.ledger.get_wallet_for_user(pi.user_id, pi.currency)
            return await self.ledger.deposit(
                wallet_id=wallet.id,
                amount=pi.amount,
                currency=pi.currency,
                fee_amount=pi.fee_amount,
                idempotency_key=f"pi_{pi.id}",
                description=pi.description or f"Deposit via PaymentIntent {pi.id}",
            )

        if purpose == PaymentIntentPurpose.WITHDRAWAL:
            wallet = await self.ledger.get_wallet_for_user(pi.user_id, pi.currency)
            return await self.ledger.withdraw(
                wallet_id=wallet.id,
                amount=pi.amount,
                currency=pi.currency,
                fee_amount=pi.fee_amount,
                idempotency_key=f"pi_{pi.id}",
                description=pi.description or f"Withdrawal via PaymentIntent {pi.id}",
            )


        if purpose == PaymentIntentPurpose.TRANSFER:
            # Same as PAYMENT for now – kept separate for future semantics
            if pi.destination_wallet_id is None:
                raise ValueError("destination_wallet_id missing for transfer")
            source_wallet = await self.ledger.get_wallet_for_user(pi.user_id, pi.currency)
            return await self.ledger.transfer(
                from_wallet_id=source_wallet.id,
                to_wallet_id=pi.destination_wallet_id,
                amount=pi.amount,
                currency=pi.currency,
                fee_amount=pi.fee_amount,
                idempotency_key=f"pi_{pi.id}",
                description=pi.description or f"Transfer via PaymentIntent {pi.id}",
            )

        raise ValueError(f"Unsupported purpose: {pi.purpose}")
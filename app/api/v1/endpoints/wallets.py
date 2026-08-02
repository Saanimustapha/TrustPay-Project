# app/api/v1/endpoints/wallets.py
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.ledger import (
    BalanceResponse,
    DepositRequest,
    TransactionResponse,
    TransferRequest,
)
from app.services.ledger import LedgerService

router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.get("/me", response_model=BalanceResponse)
async def get_my_balance(
    current_user: CurrentUser,
    db: DBSession,
    currency: str = "USD",
):
    ledger = LedgerService(db)
    wallet = await ledger.get_wallet_for_user(current_user.id, currency)
    return BalanceResponse(
        wallet_id=wallet.id,
        currency=wallet.currency,
        balance=wallet.cached_balance,
        version=wallet.version,
    )


@router.post("/me/deposit", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def deposit(
    body: DepositRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    ledger = LedgerService(db)
    wallet = await ledger.get_wallet_for_user(current_user.id, body.currency)
    reference_id = await ledger.deposit(
        wallet_id=wallet.id,
        amount=body.amount,
        currency=body.currency,
        idempotency_key=body.idempotency_key,
        description=body.description,
    )
    await db.commit()
    return TransactionResponse(reference_id=reference_id)


@router.post("/me/transfer", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def transfer(
    body: TransferRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    ledger = LedgerService(db)
    from_wallet = await ledger.get_wallet_for_user(current_user.id, body.currency)

    reference_id = await ledger.transfer(
        from_wallet_id=from_wallet.id,
        to_wallet_id=body.to_wallet_id,
        amount=body.amount,
        currency=body.currency,
        idempotency_key=body.idempotency_key,
        description=body.description,
    )
    await db.commit()
    return TransactionResponse(reference_id=reference_id)
from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.payment_intent import PaymentIntentCreate, PaymentIntentRead
from app.services.payment_intent import PaymentIntentService

router = APIRouter(prefix="/payment_intents", tags=["payment_intents"])


@router.post("", response_model=PaymentIntentRead, status_code=status.HTTP_201_CREATED)
async def create_payment_intent(
    body: PaymentIntentCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = PaymentIntentService(db)
    pi = await svc.create(
        user_id=current_user.id,
        amount=body.amount,
        currency=body.currency,
        purpose=body.purpose,
        fee_amount=body.fee_amount,
        destination_wallet_id=body.destination_wallet_id,
        idempotency_key=body.idempotency_key,
        description=body.description,
        metadata=body.metadata,
    )
    await db.commit()
    return pi


@router.post("/{pi_id}/confirm", response_model=PaymentIntentRead)
async def confirm_payment_intent(
    pi_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = PaymentIntentService(db)
    pi = await svc.confirm(pi_id, current_user.id)
    await db.commit()
    return pi


@router.post("/{pi_id}/cancel", response_model=PaymentIntentRead)
async def cancel_payment_intent(
    pi_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = PaymentIntentService(db)
    pi = await svc.cancel(pi_id, current_user.id)
    await db.commit()
    return pi


@router.get("/{pi_id}", response_model=PaymentIntentRead)
async def get_payment_intent(
    pi_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    svc = PaymentIntentService(db)
    # Re-use the locked getter for consistency (or create a non-locking version)
    pi = await svc._get_for_update(pi_id, current_user.id)
    return pi
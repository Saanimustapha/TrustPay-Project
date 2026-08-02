from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.wallet import Wallet
from app.services.auth import AuthService
from app.services.ledger import LedgerService
from app.schemas.user import UserCreate


@pytest.mark.asyncio
async def test_deposit_and_balance(db_session: AsyncSession):
    auth = AuthService(db_session)
    user = await auth.create_user(
        UserCreate(email="ledger1@example.com", password="SuperSecurePass123!")
    )
    ledger = LedgerService(db_session)
    wallet = await ledger.get_wallet_for_user(user.id)

    ref = await ledger.deposit(
        wallet_id=wallet.id,
        amount=Decimal("100.5000"),
        idempotency_key="dep-001",
    )
    await db_session.commit()

    balance = await ledger.get_balance(wallet.id)
    assert balance == Decimal("100.5000")

    # Idempotent replay
    ref2 = await ledger.deposit(
        wallet_id=wallet.id,
        amount=Decimal("100.5000"),
        idempotency_key="dep-001",
    )
    assert ref2 == ref
    balance2 = await ledger.get_balance(wallet.id)
    assert balance2 == Decimal("100.5000")  # no double credit


@pytest.mark.asyncio
async def test_transfer_success(db_session: AsyncSession):
    auth = AuthService(db_session)
    alice = await auth.create_user(
        UserCreate(email="alice2@example.com", password="SuperSecurePass123!")
    )
    bob = await auth.create_user(
        UserCreate(email="bob2@example.com", password="SuperSecurePass123!")
    )

    ledger = LedgerService(db_session)
    alice_wallet = await ledger.get_wallet_for_user(alice.id)
    bob_wallet = await ledger.get_wallet_for_user(bob.id)

    await ledger.deposit(wallet_id=alice_wallet.id, amount=Decimal("200.0000"))
    await db_session.commit()

    ref = await ledger.transfer(
        from_wallet_id=alice_wallet.id,
        to_wallet_id=bob_wallet.id,
        amount=Decimal("75.2500"),
        idempotency_key="tx-001",
    )
    await db_session.commit()

    assert await ledger.get_balance(alice_wallet.id) == Decimal("124.7500")
    assert await ledger.get_balance(bob_wallet.id) == Decimal("75.2500")


@pytest.mark.asyncio
async def test_transfer_insufficient_funds(db_session: AsyncSession):
    auth = AuthService(db_session)
    alice = await auth.create_user(
        UserCreate(email="alice3@example.com", password="SuperSecurePass123!")
    )
    bob = await auth.create_user(
        UserCreate(email="bob3@example.com", password="SuperSecurePass123!")
    )

    ledger = LedgerService(db_session)
    alice_wallet = await ledger.get_wallet_for_user(alice.id)
    bob_wallet = await ledger.get_wallet_for_user(bob.id)

    with pytest.raises(Exception):  # InsufficientFundsError
        await ledger.transfer(
            from_wallet_id=alice_wallet.id,
            to_wallet_id=bob_wallet.id,
            amount=Decimal("50.0000"),
        )


@pytest.mark.asyncio
async def test_api_deposit_and_transfer(client: AsyncClient):
    # Register two users
    await client.post(
        "/api/v1/auth/register",
        json={"email": "api_alice@example.com", "password": "SuperSecurePass123!"},
    )
    await client.post(
        "/api/v1/auth/register",
        json={"email": "api_bob@example.com", "password": "SuperSecurePass123!"},
    )

    # Login Alice
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "api_alice@example.com", "password": "SuperSecurePass123!"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Deposit
    dep = await client.post(
        "/api/v1/wallets/me/deposit",
        json={"amount": "150.0000", "idempotency_key": "api-dep-1"},
        headers=headers,
    )
    assert dep.status_code == 201

    # Check balance
    bal = await client.get("/api/v1/wallets/me", headers=headers)
    assert bal.status_code == 200
    assert Decimal(bal.json()["balance"]) == Decimal("150.0000")
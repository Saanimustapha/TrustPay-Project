from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Currency, SystemAccountType
from app.core.security import get_password_hash
from app.core.config import get_settings
from app.models.user import User
from app.models.wallet import Wallet


settings = get_settings()
SYSTEM_USER_EMAIL = settings.SYSTEM_USER_EMAIL


class SystemAccountService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache: dict[str, dict[str, UUID]] = {}

    async def _get_or_create_system_user(self) -> User:
        result = await self.db.execute(
            select(User).where(User.email == SYSTEM_USER_EMAIL)
        )
        user = result.scalar_one_or_none()
        if user:
            return user

        user = User(
            email=SYSTEM_USER_EMAIL,
            hashed_password=get_password_hash("system-account-not-for-login-ever"),
            full_name="System Accounts",
            is_active=True,
            is_verified=True,
            kyc_status="verified",
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def ensure_system_accounts(self) -> dict[str, dict[str, UUID]]:
        """
        Idempotent. Creates missing system wallets for every
        Currency × SystemAccountType combination.

        Safe to call on every application startup.
        Returns: { "USD": {"clearing": UUID, "fees": UUID, "operational": UUID}, ... }
        """
        if self._cache:
            return self._cache

        system_user = await self._get_or_create_system_user()
        mapping: dict[str, dict[str, UUID]] = {}

        for currency in Currency:
            mapping[currency.value] = {}

            for acc_type in SystemAccountType:
                result = await self.db.execute(
                    select(Wallet).where(
                        Wallet.user_id == system_user.id,
                        Wallet.currency == currency.value,
                        Wallet.account_type == acc_type.value,
                    )
                )
                wallet = result.scalar_one_or_none()

                if wallet is None:
                    wallet = Wallet(
                        user_id=system_user.id,
                        currency=currency.value,
                        account_type=acc_type.value,
                        cached_balance=0,
                    )
                    self.db.add(wallet)
                    await self.db.flush()

                mapping[currency.value][acc_type.value] = wallet.id

        await self.db.commit()
        self._cache = mapping
        return mapping

    async def get_system_wallet_id(
        self, currency: str, account_type: SystemAccountType
    ) -> UUID:
        mapping = await self.ensure_system_accounts()
        try:
            return mapping[currency][account_type.value]
        except KeyError as exc:
            raise RuntimeError(
                f"System account '{account_type.value}' for currency '{currency}' not found. "
                "Did you forget to call ensure_system_accounts()?"
            ) from exc
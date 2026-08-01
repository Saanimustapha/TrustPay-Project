from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.user import UserCreate


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_user(self, user_in: UserCreate) -> User:
        # Check uniqueness (race condition protected by unique index)
        existing = await self.get_user_by_email(user_in.email)
        if existing:
            raise ValueError("Email already registered")

        user = User(
            email=user_in.email.lower().strip(),
            hashed_password=get_password_hash(user_in.password),
            full_name=user_in.full_name,
        )
        self.db.add(user)
        await self.db.flush()          # get user.id without full commit

        # Create default USD wallet immediately (atomically)
        wallet = Wallet(user_id=user.id, currency="USD")
        self.db.add(wallet)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.get_user_by_email(email.lower().strip())
        if not user or not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user

    def create_tokens(self, user_id: UUID) -> dict[str, str]:
        return {
            "access_token": create_access_token(subject=str(user_id)),
            "refresh_token": create_refresh_token(subject=str(user_id)),
        }
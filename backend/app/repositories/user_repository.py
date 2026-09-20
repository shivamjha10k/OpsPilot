import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.scalar(select(User).where(User.id == user_id))

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email.lower()))

    async def create(
        self,
        *,
        name: str,
        email: str,
        password_hash: str,
        role,
        is_active: bool = True,
    ) -> User:
        user = User(
            name=name,
            email=email.lower(),
            password_hash=password_hash,
            role=role,
            is_active=is_active,
        )
        self.session.add(user)
        await self.session.flush()
        return user

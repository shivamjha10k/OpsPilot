from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base for SQLAlchemy models owned by Alembic."""


engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.exec_driver_sql("SELECT 1")

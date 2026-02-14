from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import settings, to_asyncpg_dsn

engine: AsyncEngine = create_async_engine(
    to_asyncpg_dsn(settings.database_url), echo=False, pool_pre_ping=True
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

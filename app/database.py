from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


engine = create_async_engine(
    settings.DATABASE_URL_ASYNC,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,   # crucial sur réseau instable (2G RDC)
    pool_recycle=1800,    # recycle les connexions toutes les 30 min
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

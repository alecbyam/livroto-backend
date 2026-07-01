import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import tous les models pour que Alembic les découvre
from app.database import Base
from app.modules.tenants.models import Tenant
from app.modules.users.models import User, RefreshToken
from app.modules.products.models import Product, Category
from app.modules.orders.models import Order, OrderItem
from app.modules.payments.models import Payment
from app.modules.location.models import LocationTracking

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    # Alembic sync driver : on utilise psycopg2 (pas asyncpg)
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine
    url = get_url().replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

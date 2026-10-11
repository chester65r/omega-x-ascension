from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from omega_api.config import normalize_database_url
from omega_api.models import Base


def make_engine(database_url: str):
    normalized_url = normalize_database_url(database_url)
    engine = create_async_engine(normalized_url, pool_pre_ping=True)
    if normalized_url.startswith('sqlite+aiosqlite:'):
        @event.listens_for(engine.sync_engine, 'connect')
        def enable_sqlite_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.close()
    return engine


def make_session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def initialize_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session

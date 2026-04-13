import logging

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def create_pool(dsn: str) -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(dsn)
    async with _pool.acquire() as conn:
        version = await conn.fetchval("SELECT version()")
    logger.info("PostgreSQL connection pool created (%s)", version)
    return _pool


def get_pool() -> asyncpg.Pool | None:
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed")

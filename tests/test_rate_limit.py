import asyncio
import time

import pytest

from app.rate_limit import AsyncTokenBucket


@pytest.mark.asyncio
async def test_disabled_bucket_never_blocks():
    bucket = AsyncTokenBucket("test", rate_per_minute=0, burst=1)
    assert not bucket.enabled
    start = time.monotonic()
    for _ in range(100):
        await bucket.acquire()
    assert time.monotonic() - start < 0.1


@pytest.mark.asyncio
async def test_burst_then_throttle():
    # 600/min = 10/s, burst=3 → 3 immediate, 4th waits ~0.1s
    bucket = AsyncTokenBucket("test", rate_per_minute=600, burst=3)
    start = time.monotonic()
    await bucket.acquire()
    await bucket.acquire()
    await bucket.acquire()
    assert time.monotonic() - start < 0.05
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert 0.08 <= elapsed <= 0.25


@pytest.mark.asyncio
async def test_concurrent_acquires_serialize():
    bucket = AsyncTokenBucket("test", rate_per_minute=600, burst=1)
    start = time.monotonic()
    await asyncio.gather(*(bucket.acquire() for _ in range(3)))
    elapsed = time.monotonic() - start
    # 1 immediate + 2 waits of 0.1s = ~0.2s
    assert elapsed >= 0.15

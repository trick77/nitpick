import asyncio

import pytest

from app.debounce import PRDebouncer


@pytest.mark.asyncio
async def test_rapid_schedules_only_run_last():
    calls: list[int] = []

    def make(n: int):
        async def _run():
            calls.append(n)
        return _run

    debouncer = PRDebouncer(delay_seconds=0.1)
    key = ("P", "r", 1)
    for i in range(5):
        debouncer.schedule(key, make(i))
        await asyncio.sleep(0.02)

    await asyncio.sleep(0.2)
    assert calls == [4]


@pytest.mark.asyncio
async def test_disabled_runs_immediately():
    calls: list[int] = []

    async def _run():
        calls.append(1)

    debouncer = PRDebouncer(delay_seconds=0)
    assert not debouncer.enabled
    debouncer.schedule(("P", "r", 1), _run)
    await asyncio.sleep(0.01)
    assert calls == [1]


@pytest.mark.asyncio
async def test_different_keys_independent():
    calls: list[str] = []

    def make(label: str):
        async def _run():
            calls.append(label)
        return _run

    debouncer = PRDebouncer(delay_seconds=0.05)
    debouncer.schedule(("P", "r", 1), make("a"))
    debouncer.schedule(("P", "r", 2), make("b"))
    await asyncio.sleep(0.15)
    assert sorted(calls) == ["a", "b"]


@pytest.mark.asyncio
async def test_exception_in_task_does_not_crash():
    async def _boom():
        raise RuntimeError("kaboom")

    debouncer = PRDebouncer(delay_seconds=0.05)
    debouncer.schedule(("P", "r", 1), _boom)
    await asyncio.sleep(0.15)
    # No exception escaped; pending map should be cleared
    assert debouncer._pending == {}


@pytest.mark.asyncio
async def test_shutdown_cancels_pending():
    ran = asyncio.Event()

    async def _run():
        ran.set()

    debouncer = PRDebouncer(delay_seconds=1.0)
    debouncer.schedule(("P", "r", 1), _run)
    await debouncer.shutdown()
    await asyncio.sleep(0.05)
    assert not ran.is_set()

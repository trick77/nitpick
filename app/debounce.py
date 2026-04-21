import asyncio
import logging
from typing import Callable, Coroutine

logger = logging.getLogger(__name__)

PRKey = tuple[str, str, int]
CoroFactory = Callable[[], Coroutine[None, None, None]]


class PRDebouncer:
    """Coalesce rapid events for the same PR into a single delayed execution.

    On each `schedule(key, ...)` call, any pending task for that key is
    cancelled and a fresh timer is started. Only the latest scheduled
    coroutine ever runs, `delay_seconds` after the final call.
    """

    def __init__(self, delay_seconds: float):
        self.delay_seconds = delay_seconds
        self._pending: dict[PRKey, asyncio.Task] = {}

    @property
    def enabled(self) -> bool:
        return self.delay_seconds > 0

    def schedule(self, key: PRKey, coro_factory: CoroFactory) -> None:
        if not self.enabled:
            asyncio.create_task(coro_factory())
            return

        existing = self._pending.get(key)
        if existing and not existing.done():
            existing.cancel()
            logger.info("debounce[%s]: superseded pending review", key)

        task = asyncio.create_task(self._run(key, coro_factory))
        self._pending[key] = task

    async def _run(self, key: PRKey, coro_factory: CoroFactory) -> None:
        try:
            await asyncio.sleep(self.delay_seconds)
        except asyncio.CancelledError:
            return
        try:
            await coro_factory()
        except Exception:
            logger.exception("debounce[%s]: task failed", key)
        finally:
            if self._pending.get(key) is asyncio.current_task():
                self._pending.pop(key, None)

    async def shutdown(self) -> None:
        tasks = list(self._pending.values())
        self._pending.clear()
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

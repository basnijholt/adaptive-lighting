"""Explicit scheduling boundaries for integration race tests."""

import asyncio
import sys
from functools import wraps


class DelayBarrier:
    """Pause one owner's coroutine at its first sleep, without changing asyncio.

    Only the selected coroutine's exact task uses this barrier. Other tasks and
    all other asyncio operations delegate to the original module. Pausing at the
    sleep itself preserves the production checks immediately after the delay.
    With all_tasks enabled, each tracked task pauses at its first sleep; arrivals
    provides a queue of the requested delays for synchronizing multiple tasks.
    """

    def __init__(self, monkeypatch, owner, method_name, *, all_tasks=False):
        """Install a module-local proxy and track invocations of one bound method."""
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.delay = None
        self.arrivals = asyncio.Queue()
        active_tasks = set()
        paused_tasks = set()
        original = getattr(owner, method_name)
        module = sys.modules[original.__module__]
        original_asyncio = module.asyncio
        barrier = self

        class ScopedAsyncio:
            """Delegate normally except for the selected task's first delay."""

            def __getattr__(self, name):
                return getattr(original_asyncio, name)

            async def sleep(self, delay, result=None):
                task = asyncio.current_task()
                if (
                    task not in active_tasks
                    or task in paused_tasks
                    or (not all_tasks and barrier.entered.is_set())
                ):
                    return await original_asyncio.sleep(delay, result)
                paused_tasks.add(task)
                if barrier.delay is None:
                    barrier.delay = delay
                barrier.arrivals.put_nowait(delay)
                barrier.entered.set()
                await asyncio.wait_for(barrier.release.wait(), 5)
                return result

        @wraps(original)
        async def tracked(*args, **kwargs):
            task = asyncio.current_task()
            active_tasks.add(task)
            try:
                return await original(*args, **kwargs)
            finally:
                active_tasks.discard(task)

        monkeypatch.setattr(module, "asyncio", ScopedAsyncio())
        monkeypatch.setattr(owner, method_name, tracked)

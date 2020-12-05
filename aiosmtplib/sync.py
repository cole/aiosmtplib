"""
Synchronous execution helpers.
"""
import asyncio
from typing import Coroutine, Optional, TypeVar

from .compat import all_tasks


__all__ = ("async_to_sync", "shutdown_loop")

CoroutineResult = TypeVar("CoroutineResult")


def async_to_sync(
    coro: Coroutine[None, None, CoroutineResult],
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> CoroutineResult:
    if loop is None:
        loop = asyncio.get_event_loop()

    if loop.is_running():
        raise RuntimeError("Event loop is already running.")

    task = loop.create_task(coro)

    try:
        result = loop.run_until_complete(task)
    finally:
        shutdown_loop(loop)

    return result


def shutdown_loop(loop: asyncio.AbstractEventLoop, timeout: float = 1.0) -> None:
    """
    Do the various dances to gently shutdown an event loop.
    """
    tasks = all_tasks(loop=loop)
    if tasks:
        for task in tasks:
            task.cancel()
        try:
            loop.run_until_complete(asyncio.wait(tasks, timeout=timeout))
        except RuntimeError:
            pass

    if not loop.is_closed():
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.call_soon(loop.stop)
        loop.run_forever()
        loop.close()

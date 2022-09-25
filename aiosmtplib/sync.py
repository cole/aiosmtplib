"""
Synchronous execution helpers.
"""
import asyncio
from typing import Coroutine, Optional, TypeVar


__all__ = ("async_to_sync",)

CoroutineResult = TypeVar("CoroutineResult")


def async_to_sync(
    coro: Coroutine[None, None, CoroutineResult],
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> CoroutineResult:
    if loop is None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        raise RuntimeError("Event loop is already running.")

    task = loop.create_task(coro)

    try:
        result = loop.run_until_complete(task)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.call_soon(loop.stop)
        loop.run_forever()
        loop.close()

    return result

"""
Synchronous execution helpers.
"""
import asyncio
from typing import Any, Awaitable, Optional

from .compat import PY36_OR_LATER, all_tasks


__all__ = ("async_to_sync", "shutdown_loop")


def async_to_sync(
    coro: Awaitable, loop: Optional[asyncio.AbstractEventLoop] = None
) -> Any:
    if loop is None:
        loop = asyncio.get_event_loop()

    if loop.is_running():
        raise RuntimeError("Event loop is already running.")

    result = loop.create_future()

    try:
        loop.run_until_complete(_await_with_future(coro, result))
    finally:
        shutdown_loop(loop)

    return result.result()


async def _await_with_future(coro: Awaitable, future: asyncio.Future) -> None:
    try:
        result = await coro
    except Exception as exc:
        future.set_exception(exc)
    else:
        future.set_result(result)


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
        if PY36_OR_LATER:
            loop.run_until_complete(loop.shutdown_asyncgens())

        loop.call_soon(loop.stop)
        loop.run_forever()
        loop.close()

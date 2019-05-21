"""
asyncio compatibility shims.
"""
import asyncio
import sys


__all__ = ("PY36_OR_LATER", "PY37_OR_LATER", "all_tasks", "get_running_loop")


PY36_OR_LATER = sys.version_info[:2] >= (3, 6)
PY37_OR_LATER = sys.version_info[:2] >= (3, 7)


def get_running_loop() -> asyncio.AbstractEventLoop:
    if PY37_OR_LATER:
        return asyncio.get_running_loop()

    return asyncio.get_event_loop()


def all_tasks(loop: asyncio.AbstractEventLoop = None):
    if PY37_OR_LATER:
        return asyncio.all_tasks(loop=loop)

    return asyncio.Task.all_tasks(loop=loop)

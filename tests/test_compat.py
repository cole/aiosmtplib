"""
Compat method tests.
"""
import asyncio
import sys

import pytest

from aiosmtplib.compat import all_tasks, get_running_loop


@pytest.mark.asyncio
async def test_get_running_loop(event_loop) -> None:
    running_loop = get_running_loop()
    assert running_loop is event_loop


def test_get_running_loop_runtime_error(event_loop) -> None:
    with pytest.raises(RuntimeError):
        get_running_loop()


@pytest.mark.asyncio
async def test_all_tasks(event_loop) -> None:
    tasks = all_tasks(event_loop)

    if sys.version_info[:2] >= (3, 7):
        current_task = asyncio.current_task(loop=event_loop)
    else:
        current_task = asyncio.Task.current_task(loop=event_loop)

    assert current_task in tasks

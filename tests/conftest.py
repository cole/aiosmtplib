"""
Pytest fixtures and config.
"""
import asyncio
import sys

import pytest

from aiosmtplib import SMTP
from testserver import SMTPPresetServer, ThreadedSMTPDServer


PY36_OR_LATER = sys.version_info[:2] >= (3, 6)
PY37_OR_LATER = sys.version_info[:2] >= (3, 7)
try:
    import uvloop
except ImportError:
    HAS_UVLOOP = False
else:
    HAS_UVLOOP = True


def pytest_addoption(parser):
    parser.addoption(
        '--event-loop', action='store', default='asyncio',
        choices=['asyncio', 'uvloop'])


@pytest.fixture()
def event_loop(request):
    loop_type = request.config.getoption('--event-loop')
    if loop_type == 'uvloop' and not HAS_UVLOOP:
        raise RuntimeError('uvloop not installed.')

    if loop_type == 'asyncio':
        loop = asyncio.new_event_loop()
    elif loop_type == 'uvloop':
        loop = uvloop.new_event_loop()
    else:
        raise ValueError('Unknown event loop type: {}'.format(loop_type))

    yield loop

    # Cancel any pending tasks
    if PY37_OR_LATER:
        cleanup_tasks = asyncio.all_tasks(loop=loop)
    else:
        cleanup_tasks = asyncio.Task.all_tasks(loop=loop)

    if cleanup_tasks:
        for task in cleanup_tasks:
            task.cancel()
        try:
            loop.run_until_complete(
                asyncio.wait(cleanup_tasks, loop=loop, timeout=0.01))
        except RuntimeError:
            # Event loop was probably already stopping.
            pass

    if PY36_OR_LATER:
        loop.run_until_complete(loop.shutdown_asyncgens())

    loop.call_soon(loop.stop)
    loop.run_forever()

    loop.close()


@pytest.fixture()
def smtpd_server(request, unused_tcp_port):
    server = ThreadedSMTPDServer('localhost', unused_tcp_port)
    server.start()

    request.addfinalizer(server.stop)

    return server


@pytest.fixture()
def preset_server(request, event_loop, unused_tcp_port):
    server = SMTPPresetServer('localhost', unused_tcp_port, loop=event_loop)

    event_loop.run_until_complete(server.start())

    def close_server():
        event_loop.run_until_complete(server.stop())

    request.addfinalizer(close_server)

    return server


@pytest.fixture()
def smtpd_client(request, smtpd_server, event_loop):
    client = SMTP(
        hostname=smtpd_server.hostname, port=smtpd_server.port,
        loop=event_loop, timeout=1)
    client.server = smtpd_server

    return client


@pytest.fixture()
def preset_client(request, preset_server, event_loop):
    client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop, timeout=1)
    client.server = preset_server

    return client

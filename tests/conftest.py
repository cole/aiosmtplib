"""
Pytest fixtures and config.
"""
import asyncio

import pytest

from aiosmtplib import SMTP

from .auth import DummySMTPAuth
from .server import (
    ThreadedPresetServer, ThreadedSMTPDServer, TLSThreadedPresetServer,
)


try:
    import uvloop
except ImportError:
    _has_uvloop = False
else:
    _has_uvloop = True


def pytest_addoption(parser):
    parser.addoption(
        '--event-loop', action='store', default='asyncio',
        choices=['asyncio', 'uvloop'])


@pytest.yield_fixture()
def event_loop(request):
    loop_type = request.config.getoption('--event-loop')
    if loop_type == 'uvloop' and not _has_uvloop:
        raise RuntimeError('uvloop not installed.')

    if loop_type == 'asyncio':
        loop = asyncio.new_event_loop()
    elif loop_type == 'uvloop':
        loop = uvloop.new_event_loop()
    else:
        raise ValueError('Unknown event loop type: {}'.format(loop_type))

    yield loop

    loop.close()


@pytest.fixture()
def smtpd_server(request, unused_tcp_port):
    server = ThreadedSMTPDServer('127.0.0.1', unused_tcp_port)
    server.start()

    request.addfinalizer(server.stop)

    return server


@pytest.fixture()
def preset_server(request, unused_tcp_port):
    server = ThreadedPresetServer('127.0.0.1', unused_tcp_port)
    server.start()

    request.addfinalizer(server.stop)

    return server


@pytest.fixture()
def tls_preset_server(request, unused_tcp_port):
    server = TLSThreadedPresetServer('127.0.0.1', unused_tcp_port)
    server.start()

    request.addfinalizer(server.stop)

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


@pytest.fixture()
def tls_preset_client(request, tls_preset_server, event_loop):
    client = SMTP(
        hostname=tls_preset_server.hostname, port=tls_preset_server.port,
        loop=event_loop, use_tls=True, validate_certs=False, timeout=1)
    client.server = tls_preset_server

    return client


@pytest.fixture()
def mock_auth(request):
    return DummySMTPAuth()

'''
Pytest fixtures and config.
'''
import pytest

from aiosmtplib import SMTP
from .server import (
    ThreadedPresetServer, SSLThreadedPresetServer, AioSMTPDTestServer,
)


@pytest.fixture()
def aiosmtpd_server(request):
    server = AioSMTPDTestServer()
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
def ssl_preset_server(request, unused_tcp_port):
    server = SSLThreadedPresetServer('127.0.0.1', unused_tcp_port)
    server.start()

    request.addfinalizer(server.stop)

    return server


@pytest.fixture()
def aiosmtpd_client(request, aiosmtpd_server, event_loop):
    client = SMTP(
        hostname=aiosmtpd_server.hostname, port=aiosmtpd_server.port,
        loop=event_loop)
    client.server = aiosmtpd_server

    return client


@pytest.fixture()
def preset_client(request, preset_server, event_loop):
    client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop)
    client.server = preset_server

    return client


@pytest.fixture()
def ssl_preset_client(request, ssl_preset_server, event_loop):
    client = SMTP(
        hostname=ssl_preset_server.hostname, port=ssl_preset_server.port,
        loop=event_loop, use_ssl=True, validate_certs=False)
    client.server = ssl_preset_server

    return client

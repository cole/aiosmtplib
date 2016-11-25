'''
Pytest fixtures and config.
'''
import pytest

from aiosmtplib import SMTP
from .server import (
    ThreadedPresetServer, TLSThreadedPresetServer, AioSMTPDTestServer,
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
def tls_preset_server(request, unused_tcp_port):
    server = TLSThreadedPresetServer('127.0.0.1', unused_tcp_port)
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
def tls_preset_client(request, tls_preset_server, event_loop):
    client = SMTP(
        hostname=tls_preset_server.hostname, port=tls_preset_server.port,
        loop=event_loop, use_tls=True, validate_certs=False)
    client.server = tls_preset_server

    return client

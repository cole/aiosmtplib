"""
Pytest fixtures and config.
"""
import pytest

from aiosmtplib import SMTP
from .server import (
    ThreadedPresetServer, TLSThreadedPresetServer,
    ThreadedSMTPDServer,
)


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
        loop=event_loop)
    client.server = smtpd_server

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

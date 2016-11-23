'''
Pytest fixtures and config.
'''
import pytest

from aiosmtplib import SMTP
from .server import PresetServer, SSLPresetServer, AioSMTPDTestServer


class ClientServerContext:
    def __init__(self, server, client):
        self.server = server
        self.client = client

    async def __aenter__(self):
        await self.server.start()
        await self.client.connect()

        return self.server, self.client

    async def __aexit__(self, exc_type, exc, traceback):
        await self.client.quit()
        await self.server.stop()


@pytest.fixture()
def aiosmtpd_server(request):
    server = AioSMTPDTestServer()
    server.start()

    request.addfinalizer(server.stop)

    return server


@pytest.fixture()
def preset_server(request, unused_tcp_port, event_loop):
    server = PresetServer('127.0.0.1', unused_tcp_port, loop=event_loop)

    return server


@pytest.fixture()
def ssl_preset_server(request, unused_tcp_port, event_loop):
    server = SSLPresetServer('127.0.0.1', unused_tcp_port, loop=event_loop)

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
        loop=preset_server.loop)
    client.server = preset_server

    return client


@pytest.fixture()
def ssl_preset_client(request, ssl_preset_server, event_loop):
    client = SMTP(
        hostname=ssl_preset_server.hostname, port=ssl_preset_server.port,
        loop=ssl_preset_server.loop, use_ssl=True, validate_certs=False)
    client.server = ssl_preset_server

    return client


@pytest.fixture()
def preset_server_client_context_manager(request, preset_client):
    return ClientServerContext(preset_client.server, preset_client)


@pytest.fixture()
def ssl_preset_server_client_context_manager(request, ssl_preset_client):
    return ClientServerContext(ssl_preset_client.server, ssl_preset_client)

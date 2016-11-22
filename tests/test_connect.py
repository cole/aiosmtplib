import pytest

import aiosmtplib  # Required so we can monkeypatch
from aiosmtplib import SMTP, SMTPConnectError, SMTPServerDisconnected


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_plain_smtp_connect(preset_server_client_context_manager):
    async with preset_server_client_context_manager as (server, client):
        assert client.is_connected


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_ssl_connection(ssl_preset_server_client_context_manager):
    async with ssl_preset_server_client_context_manager as (server, client):
        assert client.is_connected


@pytest.mark.asyncio()
async def test_quit_then_connect_ok_with_aiosmtpd(aiosmtpd_client):
    await aiosmtpd_client.connect()
    code, message = await aiosmtpd_client.quit()
    assert 200 <= code <= 299

    # Next command should fail
    with pytest.raises(SMTPServerDisconnected):
        code, message = await aiosmtpd_client.noop()

    await aiosmtpd_client.connect()

    # after reconnect, it should work again
    code, message = await aiosmtpd_client.noop()
    assert 200 <= code <= 299


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_quit_then_connect_ok_with_preset_server(
        preset_server_client_context_manager):
    async with preset_server_client_context_manager as (server, client):
        code, message = await client.quit()
        assert 200 <= code <= 299

        # Next command should fail
        with pytest.raises(SMTPServerDisconnected):
            code, message = await client.noop()

        server.next_response = b'220 Hi again!'
        await client.connect()

        # after reconnect, it should work again
        server.next_response = b'250 noop'

        code, message = await client.noop()
        assert 200 <= code <= 299


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_ssl_smtp_connect_to_non_ssl_server(preset_server):
    ssl_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=preset_server.loop,
        use_ssl=True, validate_certs=False)

    await preset_server.start()

    with pytest.raises(SMTPConnectError):
        await ssl_client.connect()
    assert not ssl_client.is_connected

    await preset_server.stop()


def test_smtp_use_ssl_with_no_ssl_raises(monkeypatch):
    monkeypatch.setattr(aiosmtplib.smtp, '_has_ssl', False)

    with pytest.raises(RuntimeError):
        SMTP(use_ssl=True)


def test_ssl_context_and_cert_raises():
    with pytest.raises(ValueError):
        SMTP(use_ssl=True, client_cert='foo.crt', ssl_context=True)

    with pytest.raises(ValueError):
        SMTP(use_ssl=True, client_key='foo.key', ssl_context=True)

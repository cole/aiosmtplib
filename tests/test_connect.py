import ssl
import smtplib
import asyncio.sslproto

import pytest

import aiosmtplib  # Required so we can monkeypatch
from aiosmtplib import SMTP, SMTPConnectError, SMTPServerDisconnected


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_plain_smtp_connect(preset_client):
    '''
    Use an explicit connect/quit here, as other tests use the context manager.
    '''
    await preset_client.connect()
    assert preset_client.is_connected

    await preset_client.quit()
    assert not preset_client.is_connected


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_tls_connection(tls_preset_client):
    '''
    Use an explicit connect/quit here, as other tests use the context manager.
    '''
    await tls_preset_client.connect()
    assert tls_preset_client.is_connected

    await tls_preset_client.quit()
    assert not tls_preset_client.is_connected


@pytest.mark.asyncio()
async def test_quit_then_connect_ok_with_aiosmtpd(aiosmtpd_client):
    async with aiosmtpd_client:
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
        preset_server, event_loop):
    preset_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop)

    response = await preset_client.connect()
    assert response.code == 220

    response = await preset_client.quit()
    assert response.code == 221

    # Next command should fail
    with pytest.raises(SMTPServerDisconnected):
        await preset_client.noop()

    response = await preset_client.connect()
    assert response.code == 220

    # after reconnect, it should work again
    preset_server.responses.append(b'250 noop')
    response = await preset_client.noop()
    assert response.code == 250

    await preset_client.quit()


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_tls_smtp_connect_to_non_tls_server(preset_server, event_loop):
    tls_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop,
        use_tls=True, validate_certs=False)

    with pytest.raises(SMTPConnectError):
        await tls_client.connect()
    assert not tls_client.is_connected


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_starttls(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'\n'.join([
            b'250-localhost, hello',
            b'250-SIZE 100000',
            b'250 STARTTLS',
        ]))
        code, message = await preset_client.ehlo()
        assert code == 250

        preset_client.server.responses.append(b'220 ready for TLS')
        code, message = await preset_client.starttls(validate_certs=False)
        assert code == 220

        # Make sure our state has been cleared
        assert not preset_client.esmtp_extensions
        assert not preset_client.supported_auth_methods
        assert not preset_client.supports_esmtp

        # make sure our connection was actually upgraded
        assert isinstance(
            preset_client.transport, asyncio.sslproto._SSLProtocolTransport)

        preset_client.server.responses.append(b'250 all good')
        code, message = await preset_client.ehlo()
        assert code == 250


def test_mock_server_starttls_with_stmplib(preset_server):
    '''
    Check that our test server behaves properly.
    '''
    smtp = smtplib.SMTP()
    smtp.connect(preset_server.hostname, preset_server.port)
    preset_server.responses.append(b'\n'.join([
        b'250-localhost, hello',
        b'250-SIZE 100000',
        b'250 STARTTLS',
    ]))

    code, message = smtp.ehlo()
    assert code == 250

    preset_server.responses.append(b'220 ready for TLS')
    code, message = smtp.starttls()
    assert code == 220

    # make sure our connection was actually upgraded
    assert isinstance(smtp.sock, ssl.SSLSocket)

    preset_server.responses.append(b'250 all good')
    code, message = smtp.ehlo()
    assert code == 250


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_smtp_use_tls_with_no_ssl_module_raises(monkeypatch, event_loop):
    monkeypatch.setattr(aiosmtplib.tls, '_has_tls', False)
    smtp = SMTP(use_tls=True, loop=event_loop)

    with pytest.raises(RuntimeError):
        await smtp.connect()


def test_tls_context_and_cert_raises():
    with pytest.raises(ValueError):
        SMTP(use_tls=True, client_cert='foo.crt', tls_context=True)

    with pytest.raises(ValueError):
        SMTP(use_tls=True, client_key='foo.key', tls_context=True)

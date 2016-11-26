import ssl
import smtplib
import asyncio.sslproto

import pytest

from aiosmtplib import SMTP, status, SMTPConnectError, SMTPServerDisconnected


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_plain_smtp_connect(preset_client):
    """
    Use an explicit connect/quit here, as other tests use the context manager.
    """
    await preset_client.connect()
    assert preset_client.is_connected

    await preset_client.quit()
    assert not preset_client.is_connected


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_tls_connection(tls_preset_client):
    """
    Use an explicit connect/quit here, as other tests use the context manager.
    """
    await tls_preset_client.connect()
    assert tls_preset_client.is_connected

    await tls_preset_client.quit()
    assert not tls_preset_client.is_connected


@pytest.mark.asyncio()
async def test_quit_then_connect_ok_with_smtpd(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.quit()
        assert response.code == status.SMTP_221_CLOSING

        # Next command should fail
        with pytest.raises(SMTPServerDisconnected):
            response = await smtpd_client.noop()

        await smtpd_client.connect()

        # after reconnect, it should work again
        response = await smtpd_client.noop()
        assert response.code == status.SMTP_250_COMPLETED


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
        preset_client.server.responses.append(b'220 ready for TLS')
        response = await preset_client.starttls(validate_certs=False)
        assert response.code == status.SMTP_220_READY

        # Make sure our state has been cleared
        assert not preset_client.esmtp_extensions
        assert not preset_client.supported_auth_methods
        assert not preset_client.supports_esmtp

        # make sure our connection was actually upgraded
        assert isinstance(
            preset_client.transport, asyncio.sslproto._SSLProtocolTransport)

        preset_client.server.responses.append(b'250 all good')
        response = await preset_client.ehlo()
        assert response.code == status.SMTP_250_COMPLETED


def test_mock_server_starttls_with_stmplib(preset_server):
    """
    Check that our test server behaves properly.
    """
    smtp = smtplib.SMTP()
    smtp._host = preset_server.hostname  # Hack around smtplib SNI bug
    smtp.connect(host=preset_server.hostname, port=preset_server.port)
    preset_server.responses.append(b'\n'.join([
        b'250-localhost, hello',
        b'250-SIZE 100000',
        b'250 STARTTLS',
    ]))

    code, message = smtp.ehlo()
    assert code == status.SMTP_250_COMPLETED

    preset_server.responses.append(b'220 ready for TLS')
    code, message = smtp.starttls()
    assert code == status.SMTP_220_READY

    # make sure our connection was actually upgraded
    assert isinstance(smtp.sock, ssl.SSLSocket)

    preset_server.responses.append(b'250 all good')
    code, message = smtp.ehlo()
    assert code == 250


def test_tls_context_and_cert_raises():
    with pytest.raises(ValueError):
        SMTP(use_tls=True, client_cert='foo.crt', tls_context=True)


@pytest.mark.asyncio
async def test_smtp_as_context_manager(smtpd_client):
    async with smtpd_client:
        assert smtpd_client.is_connected

        response = await smtpd_client.noop()
        assert response.code == status.SMTP_250_COMPLETED

    assert not smtpd_client.is_connected


@pytest.mark.asyncio
async def test_smtp_context_manager_disconnect_handling(smtpd_client):
    async with smtpd_client:
        assert smtpd_client.is_connected

        response = await smtpd_client.noop()
        assert response.code == status.SMTP_250_COMPLETED

        smtpd_client.server.stop()
        await smtpd_client.quit()

    assert not smtpd_client.is_connected


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_bad_connect_response_raises_error(preset_server, event_loop):
    preset_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop)

    preset_server.greeting = b'421 Please come back in 204232430 seconds.\n'
    with pytest.raises(SMTPConnectError):
        await preset_client.connect()

    await preset_client.close()


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_421_closes_connection(preset_server, event_loop):
    preset_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop)

    await preset_client.connect()
    preset_server.responses.append(
        b'421 Please come back in 204232430 seconds.\n')
    response = await preset_client.execute_command('NOOP')

    assert response.code == status.SMTP_421_DOMAIN_UNAVAILABLE
    assert not preset_client.is_connected

"""
Connectivity tests.
"""
import pytest

from aiosmtplib import (
    SMTP, SMTPConnectError, SMTPResponseException, SMTPServerDisconnected,
    SMTPStatus, SMTPTimeoutError,
)


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_plain_smtp_connect(preset_client):
    """
    Use an explicit connect/quit here, as other tests use the context manager.
    """
    await preset_client.connect()
    assert preset_client.is_connected

    await preset_client.quit()
    assert not preset_client.is_connected


async def test_quit_then_connect_ok_with_smtpd(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.quit()
        assert response.code == SMTPStatus.closing

        # Next command should fail
        with pytest.raises(SMTPServerDisconnected):
            response = await smtpd_client.noop()

        await smtpd_client.connect()

        # after reconnect, it should work again
        response = await smtpd_client.noop()
        assert response.code == SMTPStatus.completed


async def test_quit_then_connect_ok_with_preset_server(
        preset_server, event_loop):
    preset_client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop)

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


async def test_bad_connect_response_raises_error(preset_server, event_loop):
    preset_client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop)

    preset_server.greeting = b'421 Please come back in 204232430 seconds.\n'
    with pytest.raises(SMTPConnectError):
        await preset_client.connect()

    preset_client.close()


async def test_421_closes_connection(preset_server, event_loop):
    preset_client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop)

    await preset_client.connect()
    preset_server.responses.append(
        b'421 Please come back in 204232430 seconds.\n')

    with pytest.raises(SMTPResponseException):
        await preset_client.noop()

    assert not preset_client.is_connected


async def test_timeout_with_no_server(event_loop):
    client = SMTP(hostname='127.0.0.1', port=65534, loop=event_loop)

    with pytest.raises(SMTPTimeoutError):
        await client.connect(timeout=0.0001)


async def test_timeout_on_initial_read(preset_server, event_loop):
    client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop)

    preset_server.delay_greeting = 1

    with pytest.raises(SMTPTimeoutError):
        await client.connect(timeout=0.5)


async def test_del_client_closes_transport(preset_server, event_loop):
    preset_client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop)

    await preset_client.connect()
    transport = preset_client.transport

    del preset_client

    assert transport.is_closing()


async def test_disconnected_server_raises_on_client_read(
        preset_server, event_loop):
    preset_client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop)

    await preset_client.connect()

    preset_server.responses.append(b'250 noop')
    preset_server.drop_connection_event.set()

    with pytest.raises(SMTPServerDisconnected):
        await preset_client.execute_command(b'NOOP')

    # Verify that the connection was closed
    assert not preset_client._connect_lock.locked()
    assert preset_client.protocol is None
    assert preset_client.transport is None


async def test_disconnected_server_raises_on_client_write(
        preset_server, event_loop):
    preset_client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop)

    await preset_client.connect()

    preset_server.responses.append(b'250 noop')
    preset_server.drop_connection_event.set()

    # There seems to be a race condition here where the thread doesn't always
    # drop the connection right away, so just try twice, and one will fail
    with pytest.raises(SMTPServerDisconnected):
        await preset_client.execute_command(b'NOOP')
        await preset_client.execute_command(b'NOOP')

    # Verify that the connection was closed
    assert not preset_client._connect_lock.locked()
    assert preset_client.protocol is None
    assert preset_client.transport is None


async def test_disconnected_server_raises_on_data_read(preset_client):
    """
    The `data` command is a special case - it access protocol directly,
    rather than using `execute_command`.
    """
    await preset_client.connect()

    preset_client.server.responses.append(b'250 Hello there')
    await preset_client.ehlo()

    preset_client.server.responses.append(b'250 ok')
    await preset_client.mail('sender@example.com')

    preset_client.server.responses.append(b'250 ok')
    await preset_client.rcpt('recipient@example.com')

    preset_client.server.responses.append(b'354 lets go')
    preset_client.server.drop_connection_event.set()

    with pytest.raises(SMTPServerDisconnected):
        await preset_client.data('A MESSAGE')

    # Verify that the connection was closed
    assert not preset_client._connect_lock.locked()
    assert preset_client.protocol is None
    assert preset_client.transport is None


async def test_disconnected_server_raises_on_data_write(preset_client):
    """
    The `data` command is a special case - it access protocol directly,
    rather than using `execute_command`.
    """
    await preset_client.connect()

    preset_client.server.responses.append(b'250 Hello there')
    await preset_client.ehlo()

    preset_client.server.responses.append(b'250 ok')
    await preset_client.mail('sender@example.com')

    preset_client.server.responses.append(b'250 ok')
    await preset_client.rcpt('recipient@example.com')

    preset_client.server.responses.append(b'354 lets go')
    preset_client.server.drop_connection_event.set()

    with pytest.raises(SMTPServerDisconnected):
        await preset_client.data('A MESSAGE')

    # Verify that the connection was closed
    assert not preset_client._connect_lock.locked()
    assert preset_client.protocol is None
    assert preset_client.transport is None


async def test_disconnected_server_raises_on_starttls(preset_client):
    """
    The `data` command is a special case - it access protocol directly,
    rather than using `execute_command`.
    """
    await preset_client.connect()
    preset_client.server.responses.append(b'\n'.join([
        b'250-localhost, hello',
        b'250-SIZE 100000',
        b'250 STARTTLS',
    ]))
    await preset_client.ehlo()

    preset_client.server.responses.append(b'220 begin TLS pls')
    preset_client.server.drop_connection_event.set()

    with pytest.raises(SMTPServerDisconnected):
        await preset_client.starttls(validate_certs=False)

    # Verify that the connection was closed
    assert not preset_client._connect_lock.locked()
    assert preset_client.protocol is None
    assert preset_client.transport is None


async def test_context_manager(smtpd_client):
    async with smtpd_client:
        assert smtpd_client.is_connected

        response = await smtpd_client.noop()
        assert response.code == SMTPStatus.completed

    assert not smtpd_client.is_connected


async def test_context_manager_disconnect_handling(preset_server, event_loop):
    """
    Exceptions can be raised, but the context manager should handle
    disconnection.
    """
    preset_client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop)

    async with preset_client:
        assert preset_client.is_connected

        preset_server.responses.append(b'250 noop')
        preset_server.drop_connection_event.set()

        try:
            await preset_client.noop()
        except SMTPServerDisconnected:
            pass

    assert not preset_client.is_connected


async def test_context_manager_exception_quits(preset_server, event_loop):
    preset_client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop)

    with pytest.raises(ZeroDivisionError):
        async with preset_client:
            raise ZeroDivisionError

    assert b'QUIT' in preset_server.requests[-1]


async def test_context_manager_connect_exception_closes(
        preset_server, event_loop):
    preset_client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port,
        loop=event_loop)

    with pytest.raises(SMTPTimeoutError):
        async with preset_client:
            raise SMTPTimeoutError('Timed out!')

    assert len(preset_server.requests) == 0


async def test_context_manager_with_manual_connection(smtpd_client):
    await smtpd_client.connect()

    assert smtpd_client.is_connected

    async with smtpd_client:
        assert smtpd_client.is_connected

        await smtpd_client.quit()

        assert not smtpd_client.is_connected

    assert not smtpd_client.is_connected

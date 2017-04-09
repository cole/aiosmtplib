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


async def test_bad_connect_response_raises_error(preset_server, event_loop):
    preset_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop)

    preset_server.greeting = b'421 Please come back in 204232430 seconds.\n'
    with pytest.raises(SMTPConnectError):
        await preset_client.connect()

    preset_client.close()


async def test_421_closes_connection(preset_server, event_loop):
    preset_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop)

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


async def test_del_client_closes_transport(preset_server, event_loop):
    preset_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop)

    await preset_client.connect()
    transport = preset_client.transport

    del preset_client

    assert transport.is_closing()


async def test_disconnected_server_raises_on_client_read(
        preset_server, event_loop):
    preset_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop)

    await preset_client.connect()

    preset_server.responses.append(b'250 noop')
    preset_server.drop_connection_after_next_read = True

    with pytest.raises(SMTPServerDisconnected):
        await preset_client.execute_command(b'NOOP')

    preset_client.close()


async def test_disconnected_server_raises_on_client_write(
        preset_server, event_loop):
    preset_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop)

    await preset_client.connect()

    preset_server.responses.append(b'250 noop')
    # due to our weird server loop, it's easier just to drop on second read
    preset_server.drop_connection_before_next_read = True
    preset_server.responses.append(b'250 noop')

    await preset_client.execute_command(b'NOOP')
    with pytest.raises(SMTPServerDisconnected):
        await preset_client.execute_command(b'NOOP')

    preset_client.close()


async def test_context_manager(smtpd_client):
    async with smtpd_client:
        assert smtpd_client.is_connected

        response = await smtpd_client.noop()
        assert response.code == SMTPStatus.completed

    assert not smtpd_client.is_connected


async def test_context_manager_disconnect_handling(smtpd_client):
    async with smtpd_client:
        assert smtpd_client.is_connected

        response = await smtpd_client.noop()
        assert response.code == SMTPStatus.completed

        smtpd_client.server.stop()
        await smtpd_client.quit()

    assert not smtpd_client.is_connected


async def test_context_manager_exception_quits(preset_server, event_loop):
    preset_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop)

    with pytest.raises(ZeroDivisionError):
        async with preset_client:
            raise ZeroDivisionError

    assert b'QUIT' in preset_server.requests[-1]


async def test_context_manager_connect_exception_closes(
        preset_server, event_loop):
    preset_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop)

    with pytest.raises(SMTPTimeoutError):
        async with preset_client:
            raise SMTPTimeoutError('Timed out!')

    assert len(preset_server.requests) == 0

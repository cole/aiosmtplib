"""
Connectivity tests.
"""
import socket

import pytest

from aiosmtplib import (
    SMTP,
    SMTPConnectError,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPStatus,
)


pytestmark = pytest.mark.asyncio()


@pytest.fixture(scope="session")
def close_during_read_response_handler(request):
    async def close_during_read_response(smtpd, *args, **kwargs):
        # Read one line of data, then cut the connection.
        await smtpd.push(
            "{} End data with <CR><LF>.<CR><LF>".format(SMTPStatus.start_input)
        )

        await smtpd._reader.readline()
        smtpd.transport.close()

    return close_during_read_response


async def test_plain_smtp_connect(smtp_client, smtpd_server):
    """
    Use an explicit connect/quit here, as other tests use the context manager.
    """
    await smtp_client.connect()
    assert smtp_client.is_connected

    await smtp_client.quit()
    assert not smtp_client.is_connected


async def test_quit_then_connect_ok(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.quit()
        assert response.code == SMTPStatus.closing

        # Next command should fail
        with pytest.raises(SMTPServerDisconnected):
            response = await smtp_client.noop()

        await smtp_client.connect()

        # after reconnect, it should work again
        response = await smtp_client.noop()
        assert response.code == SMTPStatus.completed


async def test_bad_connect_response_raises_error(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    response_handler = smtpd_response_handler_factory(
        "{} retry in 5 minutes".format(SMTPStatus.domain_unavailable), close_after=True
    )
    monkeypatch.setattr(smtpd_class, "_handle_client", response_handler)

    with pytest.raises(SMTPConnectError):
        await smtp_client.connect()

    assert smtp_client.transport is None
    assert smtp_client.protocol is None


async def test_eof_on_connect_raises_connect_error(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    response_handler = smtpd_response_handler_factory(None, write_eof=True)
    monkeypatch.setattr(smtpd_class, "_handle_client", response_handler)

    with pytest.raises(SMTPConnectError):
        await smtp_client.connect()

    assert smtp_client.transport is None
    assert smtp_client.protocol is None


async def test_close_on_connect_raises_connect_error(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    response_handler = smtpd_response_handler_factory(None, close_after=True)
    monkeypatch.setattr(smtpd_class, "_handle_client", response_handler)

    with pytest.raises(SMTPConnectError):
        await smtp_client.connect()

    assert smtp_client.transport is None
    assert smtp_client.protocol is None


async def test_421_closes_connection(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    response_handler = smtpd_response_handler_factory(
        "{} Please come back in 15 seconds.".format(SMTPStatus.domain_unavailable)
    )

    monkeypatch.setattr(smtpd_class, "smtp_NOOP", response_handler)

    await smtp_client.connect()

    with pytest.raises(SMTPResponseException):
        await smtp_client.noop()

    assert not smtp_client.is_connected


async def test_connect_error_with_no_server(hostname, unused_tcp_port):
    client = SMTP(hostname=hostname, port=unused_tcp_port)

    with pytest.raises(SMTPConnectError):
        # SMTPConnectTimeoutError vs SMTPConnectError here depends on
        # processing time.
        await client.connect(timeout=1.0)


async def test_disconnected_server_raises_on_client_read(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    response_handler = smtpd_response_handler_factory(None, close_after=True)
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", response_handler)

    await smtp_client.connect()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.execute_command(b"NOOP")

    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_client_write(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    response_handler = smtpd_response_handler_factory(
        None, write_eof=True, close_after=True
    )
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", response_handler)

    await smtp_client.connect()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.execute_command(b"NOOP")

    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_data_read(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    """
    The `data` command is a special case - it accesses protocol directly,
    rather than using `execute_command`.
    """
    response_handler = smtpd_response_handler_factory(None, close_after=True)
    monkeypatch.setattr(smtpd_class, "smtp_DATA", response_handler)

    await smtp_client.connect()
    await smtp_client.ehlo()
    await smtp_client.mail("sender@example.com")
    await smtp_client.rcpt("recipient@example.com")

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.data("A MESSAGE")

    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_data_write(
    smtp_client,
    smtpd_server,
    smtpd_class,
    close_during_read_response_handler,
    monkeypatch,
):
    """
    The `data` command is a special case - it accesses protocol directly,
    rather than using `execute_command`.
    """
    monkeypatch.setattr(smtpd_class, "smtp_DATA", close_during_read_response_handler)

    await smtp_client.connect()
    await smtp_client.ehlo()
    await smtp_client.mail("sender@example.com")
    await smtp_client.rcpt("recipient@example.com")
    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.data("A MESSAGE\nLINE2")

    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_starttls(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    """
    The `starttls` command is a special case - it accesses protocol directly,
    rather than using `execute_command`.
    """
    response_handler = smtpd_response_handler_factory(None, close_after=True)
    monkeypatch.setattr(smtpd_class, "smtp_STARTTLS", response_handler)

    await smtp_client.connect()
    await smtp_client.ehlo()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.starttls(validate_certs=False, timeout=1.0)

    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_context_manager(smtp_client, smtpd_server):
    async with smtp_client:
        assert smtp_client.is_connected

        response = await smtp_client.noop()
        assert response.code == SMTPStatus.completed

    assert not smtp_client.is_connected


async def test_context_manager_disconnect_handling(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    """
    Exceptions can be raised, but the context manager should handle
    disconnection.
    """
    response_handler = smtpd_response_handler_factory(None, close_after=True)
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", response_handler)

    async with smtp_client:
        assert smtp_client.is_connected

        try:
            await smtp_client.noop()
        except SMTPServerDisconnected:
            pass

    assert not smtp_client.is_connected


async def test_context_manager_exception_quits(
    smtp_client, smtpd_server, received_commands
):
    with pytest.raises(ZeroDivisionError):
        async with smtp_client:
            1 / 0

    assert received_commands[-1][0] == "QUIT"


async def test_context_manager_connect_exception_closes(
    smtp_client, smtpd_server, received_commands
):
    with pytest.raises(ConnectionError):
        async with smtp_client:
            raise ConnectionError("Failed!")

    assert len(received_commands) == 0


async def test_context_manager_with_manual_connection(smtp_client, smtpd_server):
    await smtp_client.connect()

    assert smtp_client.is_connected

    async with smtp_client:
        assert smtp_client.is_connected

        await smtp_client.quit()

        assert not smtp_client.is_connected

    assert not smtp_client.is_connected


async def test_context_manager_double_entry(smtp_client, smtpd_server):
    async with smtp_client:
        async with smtp_client:
            assert smtp_client.is_connected
            response = await smtp_client.noop()
            assert response.code == SMTPStatus.completed

        # The first exit should disconnect us
        assert not smtp_client.is_connected
    assert not smtp_client.is_connected


async def test_connect_error_second_attempt(hostname, unused_tcp_port):
    client = SMTP(hostname=hostname, port=unused_tcp_port, timeout=1.0)

    with pytest.raises(SMTPConnectError):
        await client.connect()

    with pytest.raises(SMTPConnectError):
        await client.connect()


async def test_server_unexpected_disconnect(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    response_handler = smtpd_response_handler_factory(
        "{} OK".format(SMTPStatus.completed),
        second_response_text="{} Bye now!".format(SMTPStatus.closing),
        close_after=True,
    )

    monkeypatch.setattr(smtpd_class, "smtp_EHLO", response_handler)

    await smtp_client.connect()
    await smtp_client.ehlo()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.noop()


async def test_connect_with_login(
    smtp_client, smtpd_server, message, received_messages, received_commands
):
    # STARTTLS is required for login
    await smtp_client.connect(  # nosec
        start_tls=True, validate_certs=False, username="test", password="test"
    )

    assert "AUTH" in [command[0] for command in received_commands]

    await smtp_client.quit()


async def test_connect_via_socket(smtp_client, hostname, smtpd_server_port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((hostname, smtpd_server_port))

        await smtp_client.connect(hostname=None, port=None, sock=sock)
        response = await smtp_client.ehlo()

    assert response.code == SMTPStatus.completed


async def test_connect_via_socket_path(
    smtp_client, smtpd_server_socket_path, socket_path
):
    await smtp_client.connect(hostname=None, port=None, socket_path=socket_path)
    response = await smtp_client.ehlo()

    assert response.code == SMTPStatus.completed

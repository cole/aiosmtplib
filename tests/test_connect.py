"""
Connectivity tests.
"""
import pytest

from aiosmtplib import (
    SMTP,
    SMTPConnectError,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPStatus,
)


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


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
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    async def handle_client(self):
        await self.push("421 Please come back in 204232430 seconds.")
        self.transport.close()

    monkeypatch.setattr(smtpd_class, "_handle_client", handle_client)

    with pytest.raises(SMTPConnectError):
        await smtp_client.connect()

    assert smtp_client.transport is None
    assert smtp_client.protocol is None


async def test_421_closes_connection(
    smtp_client, smtpd_server, smtpd_handler, monkeypatch
):
    monkeypatch.setattr(
        smtpd_handler, "NOOP_response_message", "421 Please come back in 15 seconds."
    )

    await smtp_client.connect()

    with pytest.raises(SMTPResponseException):
        await smtp_client.noop()

    assert not smtp_client.is_connected


async def test_connect_error_with_no_server(event_loop, hostname, port):
    client = SMTP(hostname=hostname, port=port, loop=event_loop)

    with pytest.raises(SMTPConnectError):
        # SMTPTimeoutError vs SMTPConnectError here depends on processing time.
        await client.connect(timeout=1.0)


async def test_disconnected_server_raises_on_client_read(
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    async def noop_response(self, arg):
        self.transport.close()

    monkeypatch.setattr(smtpd_class, "smtp_NOOP", noop_response)

    await smtp_client.connect()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.execute_command(b"NOOP")

    # Verify that the connection was closed
    assert not smtp_client._connect_lock.locked()
    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_client_write(
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    async def noop_response(self, arg):
        self.transport.write_eof()
        self.transport.close()
        await self.push("250 ok")

    monkeypatch.setattr(smtpd_class, "smtp_NOOP", noop_response)

    await smtp_client.connect()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.execute_command(b"NOOP")

    # Verify that the connection was closed
    assert not smtp_client._connect_lock.locked()
    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_data_read(
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    """
    The `data` command is a special case - it accesses protocol directly,
    rather than using `execute_command`.
    """

    async def data_response(self, arg):
        self.transport.close()
        await self.push("250 ok")

    monkeypatch.setattr(smtpd_class, "smtp_DATA", data_response)

    await smtp_client.connect()
    await smtp_client.ehlo()
    await smtp_client.mail("sender@example.com")
    await smtp_client.rcpt("recipient@example.com")

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.data("A MESSAGE")

    # Verify that the connection was closed
    assert not smtp_client._connect_lock.locked()
    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_data_write(
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    """
    The `data` command is a special case - it accesses protocol directly,
    rather than using `execute_command`.
    """

    async def data_handler(self, arg):
        # Read one line of data, then cut the connection.
        await self.push("354 End data with <CR><LF>.<CR><LF>")

        await self._reader.readline()
        self.transport.close()

    monkeypatch.setattr(smtpd_class, "smtp_DATA", data_handler)

    await smtp_client.connect()
    await smtp_client.ehlo()
    await smtp_client.mail("sender@example.com")
    await smtp_client.rcpt("recipient@example.com")
    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.data("A MESSAGE\nLINE2")

    # Verify that the connection was closed
    assert not smtp_client._connect_lock.locked()
    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_starttls(
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    """
    The `starttls` command is a special case - it accesses protocol directly,
    rather than using `execute_command`.
    """

    async def starttls_handler(self, arg):
        self.transport.close()

    monkeypatch.setattr(smtpd_class, "smtp_STARTTLS", starttls_handler)

    await smtp_client.connect()
    await smtp_client.ehlo()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.starttls(validate_certs=False, timeout=1.0)

    # Verify that the connection was closed
    assert not smtp_client._connect_lock.locked()
    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_context_manager(smtp_client, smtpd_server):
    async with smtp_client:
        assert smtp_client.is_connected

        response = await smtp_client.noop()
        assert response.code == SMTPStatus.completed

    assert not smtp_client.is_connected


async def test_context_manager_disconnect_handling(
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    """
    Exceptions can be raised, but the context manager should handle
    disconnection.
    """

    async def noop_response(self, arg):
        self.transport.close()
        await self.push("250 OK")

    monkeypatch.setattr(smtpd_class, "smtp_NOOP", noop_response)

    async with smtp_client:
        assert smtp_client.is_connected

        try:
            await smtp_client.noop()
        except SMTPServerDisconnected:
            pass

    assert not smtp_client.is_connected


async def test_context_manager_exception_quits(
    smtp_client, smtpd_server, recieved_commands
):
    with pytest.raises(ZeroDivisionError):
        async with smtp_client:
            1 / 0

    assert recieved_commands[-1][0] == "QUIT"


async def test_context_manager_connect_exception_closes(
    smtp_client, smtpd_server, recieved_commands
):
    with pytest.raises(ConnectionError):
        async with smtp_client:
            raise ConnectionError("Failed!")

    assert len(recieved_commands) == 0


async def test_context_manager_with_manual_connection(smtp_client, smtpd_server):
    await smtp_client.connect()

    assert smtp_client.is_connected

    async with smtp_client:
        assert smtp_client.is_connected

        await smtp_client.quit()

        assert not smtp_client.is_connected

    assert not smtp_client.is_connected


async def test_connect_error_second_attempt(event_loop, hostname, port):
    client = SMTP(hostname=hostname, port=port, loop=event_loop, timeout=1.0)

    with pytest.raises(SMTPConnectError):
        await client.connect()

    with pytest.raises(SMTPConnectError):
        await client.connect()

"""
Connectivity tests.
"""
import asyncio

import pytest

from aiosmtplib import (
    SMTP,
    SMTPConnectError,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPStatus,
    SMTPTimeoutError,
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
    smtp_client, smtpd_server, aiosmtpd_class, monkeypatch
):
    async def handle_client(self):
        await self.push("421 Please come back in 204232430 seconds.")
        self.transport.close()

    monkeypatch.setattr(aiosmtpd_class, "_handle_client", handle_client)

    with pytest.raises(SMTPConnectError):
        await smtp_client.connect()

    smtp_client.close()


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
        await client.connect(timeout=1)


async def test_timeout_error_with_no_server(event_loop, hostname, port):
    client = SMTP(hostname=hostname, port=port, loop=event_loop)

    with pytest.raises(SMTPTimeoutError):
        # SMTPTimeoutError vs SMTPConnectError here depends on processing time.
        await client.connect(timeout=0.000000001)


async def test_timeout_on_initial_read(
    smtp_client, smtpd_server, aiosmtpd_class, monkeypatch, event_loop
):
    async def handle_client(self):
        await asyncio.sleep(0.1, loop=event_loop)

    monkeypatch.setattr(aiosmtpd_class, "_handle_client", handle_client)

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.connect(timeout=0.01)


async def test_timeout_on_starttls(
    smtp_client, starttls_smtpd_server, aiosmtpd_class, monkeypatch, event_loop
):
    async def handle_starttls(self, arg):
        await asyncio.sleep(0.1, loop=event_loop)

    monkeypatch.setattr(aiosmtpd_class, "smtp_STARTTLS", handle_starttls)

    await smtp_client.connect()
    await smtp_client.ehlo()

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.starttls(validate_certs=False, timeout=0.01)


async def test_disconnected_server_raises_on_client_read(
    smtp_client, smtpd_server, aiosmtpd_class, monkeypatch
):
    async def noop_response(self, arg):
        self.transport.close()

    monkeypatch.setattr(aiosmtpd_class, "smtp_NOOP", noop_response)

    await smtp_client.connect()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.execute_command(b"NOOP")

    # Verify that the connection was closed
    assert not smtp_client._connect_lock.locked()
    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_client_write(
    smtp_client, smtpd_server, aiosmtpd_class, monkeypatch
):
    async def noop_response(self, arg):
        self.transport.write_eof()
        self.transport.close()
        await self.push("250 ok")

    monkeypatch.setattr(aiosmtpd_class, "smtp_NOOP", noop_response)

    await smtp_client.connect()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.execute_command(b"NOOP")

    # Verify that the connection was closed
    assert not smtp_client._connect_lock.locked()
    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_data_read(
    smtp_client, smtpd_server, aiosmtpd_class, monkeypatch
):
    """
    The `data` command is a special case - it accesses protocol directly,
    rather than using `execute_command`.
    """

    async def data_response(self, arg):
        self.transport.close()
        await self.push("250 ok")

    monkeypatch.setattr(aiosmtpd_class, "smtp_DATA", data_response)

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


async def test_disconnected_server_raises_on_data_write(preset_client):
    """
    The `data` command is a special case - it accesses protocol directly,
    rather than using `execute_command`.
    """
    await preset_client.connect()

    preset_client.server.responses.append(b"250 Hello there")
    await preset_client.ehlo()

    preset_client.server.responses.append(b"250 ok")
    await preset_client.mail("sender@example.com")

    preset_client.server.responses.append(b"250 ok")
    await preset_client.rcpt("recipient@example.com")

    preset_client.server.responses.append(b"354 lets go")
    preset_client.server.drop_connection_after_request = b"A MESS"

    with pytest.raises(SMTPServerDisconnected):
        await preset_client.data("A MESSAGE")

    # Verify that the connection was closed
    assert not preset_client._connect_lock.locked()
    assert preset_client.protocol is None
    assert preset_client.transport is None


async def test_disconnected_server_raises_on_starttls(preset_client):
    """
    The `starttls` command is a special case - it accesses protocol directly,
    rather than using `execute_command`.
    """
    await preset_client.connect()
    preset_client.server.responses.append(
        b"\n".join([b"250-localhost, hello", b"250-SIZE 100000", b"250 STARTTLS"])
    )
    await preset_client.ehlo()

    preset_client.server.responses.append(b"220 begin TLS pls")
    preset_client.server.drop_connection_event.set()

    with pytest.raises(SMTPServerDisconnected):
        await preset_client.starttls(validate_certs=False)

    # Verify that the connection was closed
    assert not preset_client._connect_lock.locked()
    assert preset_client.protocol is None
    assert preset_client.transport is None


async def test_context_manager(smtp_client, smtpd_server):
    async with smtp_client:
        assert smtp_client.is_connected

        response = await smtp_client.noop()
        assert response.code == SMTPStatus.completed

    assert not smtp_client.is_connected


async def test_context_manager_disconnect_handling(
    smtp_client, smtpd_server, aiosmtpd_class, monkeypatch
):
    """
    Exceptions can be raised, but the context manager should handle
    disconnection.
    """

    async def noop_response(self, arg):
        self.transport.close()
        await self.push("250 OK")

    monkeypatch.setattr(aiosmtpd_class, "smtp_NOOP", noop_response)

    async with smtp_client:
        assert smtp_client.is_connected

        try:
            await smtp_client.noop()
        except SMTPServerDisconnected:
            pass

    assert not smtp_client.is_connected


async def test_context_manager_exception_quits(
    smtp_client, smtpd_server, smtpd_commands
):
    with pytest.raises(ZeroDivisionError):
        async with smtp_client:
            1 / 0

    assert smtpd_commands[-1][0] == "QUIT"


async def test_context_manager_connect_exception_closes(
    smtp_client, smtpd_server, smtpd_commands
):
    with pytest.raises(SMTPTimeoutError):
        async with smtp_client:
            raise SMTPTimeoutError("Timed out!")

    assert len(smtpd_commands) == 0


async def test_context_manager_with_manual_connection(smtp_client, smtpd_server):
    await smtp_client.connect()

    assert smtp_client.is_connected

    async with smtp_client:
        assert smtp_client.is_connected

        await smtp_client.quit()

        assert not smtp_client.is_connected

    assert not smtp_client.is_connected


async def test_connect_error_second_attempt(event_loop, hostname, port):
    client = SMTP(hostname=hostname, port=port, loop=event_loop)

    with pytest.raises(SMTPConnectError):
        await client.connect(timeout=0.01)

    with pytest.raises(SMTPConnectError):
        await client.connect(timeout=0.01)

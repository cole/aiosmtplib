"""
Connectivity tests.
"""
import asyncio
import pathlib
import socket
from typing import Any, Callable, List, Tuple, Type, Union

import pytest
from aiosmtpd.smtp import SMTP as SMTPD

from aiosmtplib import (
    SMTP,
    SMTPConnectError,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPStatus,
)


pytestmark = pytest.mark.asyncio()


async def close_during_read_response(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    # Read one line of data, then cut the connection.
    await smtpd.push(f"{SMTPStatus.start_input} End data with <CR><LF>.<CR><LF>")

    await smtpd._reader.readline()
    smtpd.transport.close()


async def test_plain_smtp_connect(
    smtp_client: SMTP, smtpd_server: asyncio.AbstractServer
) -> None:
    """
    Use an explicit connect/quit here, as other tests use the context manager.
    """
    await smtp_client.connect()
    assert smtp_client.is_connected

    await smtp_client.quit()
    assert not smtp_client.is_connected


async def test_quit_then_connect_ok(
    smtp_client: SMTP, smtpd_server: asyncio.AbstractServer
) -> None:
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
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_unavailable: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "_handle_client", smtpd_mock_response_unavailable)

    with pytest.raises(SMTPConnectError):
        await smtp_client.connect()

    assert smtp_client.transport is None
    assert smtp_client.protocol is None


async def test_eof_on_connect_raises_connect_error(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_eof: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "_handle_client", smtpd_mock_response_eof)

    with pytest.raises(SMTPConnectError):
        await smtp_client.connect()

    assert smtp_client.transport is None
    assert smtp_client.protocol is None


async def test_close_on_connect_raises_connect_error(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_disconnect: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "_handle_client", smtpd_mock_response_disconnect)

    with pytest.raises(SMTPConnectError):
        await smtp_client.connect()

    assert smtp_client.transport is None
    assert smtp_client.protocol is None


async def test_421_closes_connection(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_unavailable: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", smtpd_mock_response_unavailable)

    await smtp_client.connect()

    with pytest.raises(SMTPResponseException):
        await smtp_client.noop()

    assert not smtp_client.is_connected


async def test_connect_error_with_no_server(
    hostname: str, unused_tcp_port: int
) -> None:
    client = SMTP(hostname=hostname, port=unused_tcp_port)

    with pytest.raises(SMTPConnectError):
        # SMTPConnectTimeoutError vs SMTPConnectError here depends on
        # processing time.
        await client.connect(timeout=1.0)


async def test_disconnected_server_raises_on_client_read(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_disconnect: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", smtpd_mock_response_disconnect)

    await smtp_client.connect()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.execute_command(b"NOOP")

    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_client_write(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_eof: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", smtpd_mock_response_eof)

    await smtp_client.connect()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.execute_command(b"NOOP")

    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_data_read(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_disconnect: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_DATA", smtpd_mock_response_disconnect)

    await smtp_client.connect()
    await smtp_client.ehlo()
    await smtp_client.mail("sender@example.com")
    await smtp_client.rcpt("recipient@example.com")

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.data("A MESSAGE")

    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_data_write(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_DATA", close_during_read_response)

    await smtp_client.connect()
    await smtp_client.ehlo()
    await smtp_client.mail("sender@example.com")
    await smtp_client.rcpt("recipient@example.com")
    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.data("A MESSAGE\nLINE2")

    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_disconnected_server_raises_on_starttls(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_disconnect: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_STARTTLS", smtpd_mock_response_disconnect)

    await smtp_client.connect()
    await smtp_client.ehlo()

    async def mock_ehlo_or_helo_if_needed() -> None:
        pass

    smtp_client._ehlo_or_helo_if_needed = mock_ehlo_or_helo_if_needed  # type: ignore

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.starttls(timeout=1.0)

    assert smtp_client.protocol is None
    assert smtp_client.transport is None


async def test_context_manager(
    smtp_client: SMTP, smtpd_server: asyncio.AbstractServer
) -> None:
    async with smtp_client:
        assert smtp_client.is_connected

        response = await smtp_client.noop()
        assert response.code == SMTPStatus.completed

    assert not smtp_client.is_connected


async def test_context_manager_disconnect_handling(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_disconnect: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Exceptions can be raised, but the context manager should handle
    disconnection.
    """
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", smtpd_mock_response_disconnect)

    async with smtp_client:
        assert smtp_client.is_connected

        try:
            await smtp_client.noop()
        except SMTPServerDisconnected:
            pass

    assert not smtp_client.is_connected


async def test_context_manager_exception_quits(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    received_commands: List[Tuple[str, Tuple[Any, ...]]],
) -> None:
    with pytest.raises(ZeroDivisionError):
        async with smtp_client:
            1 / 0  # noqa

    assert received_commands[-1][0] == "QUIT"


async def test_context_manager_connect_exception_closes(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    received_commands: List[Tuple[str, Tuple[Any, ...]]],
) -> None:
    with pytest.raises(ConnectionError):
        async with smtp_client:
            raise ConnectionError("Failed!")

    assert len(received_commands) == 0


async def test_context_manager_with_manual_connection(
    smtp_client: SMTP, smtpd_server: asyncio.AbstractServer
) -> None:
    await smtp_client.connect()

    assert smtp_client.is_connected

    async with smtp_client:
        assert smtp_client.is_connected

        await smtp_client.quit()

        assert not smtp_client.is_connected

    assert not smtp_client.is_connected


async def test_context_manager_double_entry(
    smtp_client: SMTP, smtpd_server: asyncio.AbstractServer
) -> None:
    async with smtp_client:
        async with smtp_client:
            assert smtp_client.is_connected
            response = await smtp_client.noop()
            assert response.code == SMTPStatus.completed

        # The first exit should disconnect us
        assert not smtp_client.is_connected
    assert not smtp_client.is_connected


async def test_connect_error_second_attempt(
    hostname: str, unused_tcp_port: int
) -> None:
    client = SMTP(hostname=hostname, port=unused_tcp_port, timeout=1.0)

    with pytest.raises(SMTPConnectError):
        await client.connect()

    with pytest.raises(SMTPConnectError):
        await client.connect()


async def test_server_unexpected_disconnect(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_done_then_close: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_EHLO", smtpd_mock_response_done_then_close)

    await smtp_client.connect()
    await smtp_client.ehlo()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.noop()


async def test_connect_with_login(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    received_commands: List[Tuple[str, Tuple[Any, ...]]],
    auth_username: str,
    auth_password: str,
) -> None:
    # STARTTLS is required for login
    await smtp_client.connect(
        start_tls=True,
        username=auth_username,
        password=auth_password,
    )

    assert "AUTH" in [command[0] for command in received_commands]

    await smtp_client.quit()


async def test_connect_via_socket(
    smtp_client: SMTP, hostname: str, smtpd_server_port: int
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((hostname, smtpd_server_port))

        await smtp_client.connect(hostname=None, port=None, sock=sock)
        response = await smtp_client.ehlo()

    assert response.code == SMTPStatus.completed


async def test_connect_via_socket_path(
    smtp_client: SMTP,
    smtpd_server_socket_path: asyncio.AbstractServer,
    socket_path: Union[pathlib.Path, str, bytes],
) -> None:
    await smtp_client.connect(hostname=None, port=None, socket_path=socket_path)
    response = await smtp_client.ehlo()

    assert response.code == SMTPStatus.completed


async def test_disconnected_server_get_transport_info(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_eof: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", smtpd_mock_response_eof)

    await smtp_client.connect()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.execute_command(b"NOOP")

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.get_transport_info("sslcontext")


async def test_disconnected_server_data(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_eof: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", smtpd_mock_response_eof)

    await smtp_client.connect()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.execute_command(b"NOOP")

    async def mock_ehlo_or_helo_if_needed() -> None:
        pass

    smtp_client._ehlo_or_helo_if_needed = mock_ehlo_or_helo_if_needed  # type: ignore

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.data("123")

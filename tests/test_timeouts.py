"""
Timeout tests.
"""
import asyncio
import socket
import ssl
from typing import Callable, Type

import pytest
from aiosmtpd.smtp import SMTP as SMTPD

from aiosmtplib import (
    SMTP,
    SMTPConnectTimeoutError,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)
from aiosmtplib.protocol import SMTPProtocol


pytestmark = pytest.mark.asyncio()


async def test_command_timeout_error(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_delayed_ok: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_EHLO", smtpd_mock_response_delayed_ok)

    await smtp_client.connect()

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.ehlo("example.com", timeout=0.0)


async def test_data_timeout_error(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_delayed_ok: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_DATA", smtpd_mock_response_delayed_ok)

    await smtp_client.connect()
    await smtp_client.ehlo()
    await smtp_client.mail("j@example.com")
    await smtp_client.rcpt("test@example.com")
    with pytest.raises(SMTPTimeoutError):
        await smtp_client.data("HELLO WORLD", timeout=0.0)


async def test_timeout_error_on_connect(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_delayed_ok: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "_handle_client", smtpd_mock_response_delayed_ok)

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.connect(timeout=0.0)

    assert smtp_client.transport is None
    assert smtp_client.protocol is None


async def test_timeout_on_initial_read(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_delayed_read: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "_handle_client", smtpd_mock_response_delayed_read)

    with pytest.raises(SMTPTimeoutError):
        # We need to use a timeout > 0 here to avoid timing out on connect
        await smtp_client.connect(timeout=0.01)


async def test_timeout_on_starttls(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_delayed_ok: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_STARTTLS", smtpd_mock_response_delayed_ok)

    await smtp_client.connect()
    await smtp_client.ehlo()

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.starttls(timeout=0.0)


async def test_protocol_read_response_with_timeout_times_out(
    event_loop: asyncio.AbstractEventLoop,
    echo_server: asyncio.AbstractServer,
    hostname: str,
    echo_server_port: int,
) -> None:
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=echo_server_port
    )

    transport, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    with pytest.raises(SMTPTimeoutError) as exc:
        await protocol.read_response(timeout=0.0)

    transport.close()

    assert str(exc.value) == "Timed out waiting for server response"


async def test_connect_timeout_error(hostname: str, unused_tcp_port: int) -> None:
    client = SMTP(hostname=hostname, port=unused_tcp_port, timeout=0.0)

    with pytest.raises(SMTPConnectTimeoutError) as exc:
        await client.connect()

    expected_message = f"Timed out connecting to {hostname} on port {unused_tcp_port}"
    assert str(exc.value) == expected_message


async def test_server_disconnected_error_after_connect_timeout(
    hostname: str,
    unused_tcp_port: int,
    sender_str: str,
    recipient_str: str,
    message_str: str,
) -> None:
    client = SMTP(hostname=hostname, port=unused_tcp_port)

    with pytest.raises(SMTPConnectTimeoutError):
        await client.connect(timeout=0.0)

    with pytest.raises(SMTPServerDisconnected):
        await client.sendmail(sender_str, [recipient_str], message_str)


async def test_protocol_timeout_on_starttls(
    event_loop: asyncio.AbstractEventLoop,
    bind_address: str,
    hostname: str,
    client_tls_context: ssl.SSLContext,
) -> None:
    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await asyncio.sleep(1.0)

    server = await asyncio.start_server(
        client_connected, host=bind_address, port=0, family=socket.AF_INET
    )
    server_port = server.sockets[0].getsockname()[1] if server.sockets else 0

    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=server_port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    with pytest.raises(SMTPTimeoutError):
        # STARTTLS timeout must be > 0
        await protocol.start_tls(client_tls_context, timeout=0.00001)

    server.close()
    await server.wait_closed()

"""
Timeout tests.
"""

import asyncio
import socket
import ssl

import pytest

from aiosmtplib import (
    SMTP,
    SMTPConnectTimeoutError,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)
from aiosmtplib.protocol import SMTPProtocol

from .compat import cleanup_server
from .smtpd import mock_response_delayed_ok, mock_response_delayed_read


@pytest.mark.smtpd_mocks(smtp_EHLO=mock_response_delayed_ok)
async def test_command_timeout_error(smtp_client: SMTP) -> None:
    await smtp_client.connect()

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.ehlo(hostname="example.com", timeout=0.0)


@pytest.mark.smtpd_mocks(smtp_DATA=mock_response_delayed_ok)
async def test_data_timeout_error(smtp_client: SMTP) -> None:
    await smtp_client.connect()
    await smtp_client.ehlo()
    await smtp_client.mail("j@example.com")
    await smtp_client.rcpt("test@example.com")
    with pytest.raises(SMTPTimeoutError):
        await smtp_client.data("HELLO WORLD", timeout=0.0)


@pytest.mark.smtpd_mocks(_handle_client=mock_response_delayed_ok)
async def test_timeout_error_on_connect(smtp_client: SMTP) -> None:
    with pytest.raises(SMTPTimeoutError):
        await smtp_client.connect(timeout=0.0)

    assert smtp_client.transport is None
    assert smtp_client.protocol is None


@pytest.mark.smtpd_mocks(_handle_client=mock_response_delayed_read)
async def test_timeout_on_initial_read(smtp_client: SMTP) -> None:
    with pytest.raises(SMTPTimeoutError):
        # We need to use a timeout > 0 here to avoid timing out on connect
        await smtp_client.connect(timeout=0.01)


@pytest.mark.smtpd_mocks(smtp_STARTTLS=mock_response_delayed_ok)
async def test_timeout_on_starttls(smtp_client: SMTP) -> None:
    await smtp_client.connect()
    await smtp_client.ehlo()

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.starttls(timeout=0.0)


async def test_protocol_read_response_with_timeout_times_out(
    echo_server: asyncio.AbstractServer,
    hostname: str,
    echo_server_port: int,
) -> None:
    event_loop = asyncio.get_running_loop()

    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=echo_server_port
    )

    transport, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    with pytest.raises(SMTPTimeoutError) as exc:
        await protocol.read_response(timeout=0.0)  # type: ignore

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
    bind_address: str,
    hostname: str,
    client_tls_context: ssl.SSLContext,
) -> None:
    event_loop = asyncio.get_running_loop()

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
        await protocol.start_tls(client_tls_context, timeout=0.00001)  # type: ignore

    server.close()
    await cleanup_server(server)


async def test_protocol_connection_aborted_on_starttls(
    hostname: str,
    smtpd_server_port: int,
    client_tls_context: ssl.SSLContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_loop = asyncio.get_running_loop()

    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=smtpd_server_port
    )
    transport, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    def mock_start_tls(*args, **kwargs) -> None:
        raise ConnectionAbortedError("Connection was aborted")

    monkeypatch.setattr(event_loop, "start_tls", mock_start_tls)

    with pytest.raises(SMTPTimeoutError):
        await protocol.start_tls(client_tls_context)

    transport.close()

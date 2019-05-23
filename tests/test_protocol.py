"""
Protocol level tests.
"""
import asyncio

import pytest

from aiosmtplib import SMTPResponseException, SMTPServerDisconnected
from aiosmtplib.protocol import SMTPProtocol


pytestmark = pytest.mark.asyncio()


async def test_protocol_connect(echo_server, event_loop, hostname, port):
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=port
    )
    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    assert isinstance(protocol._stream_reader, asyncio.StreamReader)
    assert isinstance(protocol._stream_writer, asyncio.StreamWriter)
    assert protocol._stream_reader._transport is not None
    assert not protocol._stream_reader._transport.is_closing()

    protocol._stream_writer.close()


async def test_protocol_read_limit_overrun(event_loop, hostname, port, monkeypatch):
    async def client_connected(reader, writer):
        await reader.read(1000)
        long_response = (
            b"220 At vero eos et accusamus et iusto odio dignissimos ducimus qui "
            b"blanditiis praesentium voluptatum deleniti atque corruptis qui "
            b"blanditiis praesentium voluptatum\n"
        )
        writer.write(long_response)
        await writer.drain()

    server = await asyncio.start_server(client_connected, host=hostname, port=port)
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    monkeypatch.setattr(protocol._stream_reader, "_limit", 128)

    with pytest.raises(SMTPResponseException) as exc_info:
        await protocol.execute_command(b"TEST\n", timeout=1.0)

    assert exc_info.value.code == 500
    assert "Line too long" in exc_info.value.message

    server.close()
    await server.wait_closed()


async def test_protocol_connected_check_on_read_response(monkeypatch):
    protocol = SMTPProtocol()
    monkeypatch.setattr(protocol, "_stream_reader", None)

    with pytest.raises(SMTPServerDisconnected):
        await protocol.read_response(timeout=1.0)


async def test_protocol_connected_check_on_write_and_drain():
    smtp_protocol = SMTPProtocol()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.write_and_drain(b"foo", timeout=1.0)


async def test_protocol_reader_connected_check_on_start_tls(client_tls_context):
    smtp_protocol = SMTPProtocol()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.start_tls(client_tls_context, timeout=1.0)


async def test_protocol_writer_connected_check_on_start_tls(client_tls_context):
    smtp_protocol = SMTPProtocol()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.start_tls(client_tls_context)


async def test_protocol_starttls_compatibility(client_tls_context):
    smtp_protocol = SMTPProtocol()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.starttls(client_tls_context)


async def test_connectionerror_on_drain_writer(event_loop, echo_server, hostname, port):
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    protocol.pause_writing()
    protocol._stream_reader._transport.close()

    with pytest.raises(ConnectionError):
        await protocol._stream_writer.drain_with_timeout(timeout=1.0)


async def test_incompletereaderror_on_readline_with_partial_line(
    event_loop, hostname, port
):
    partial_response = b"499 incomplete response\\"

    async def client_connected(reader, writer):
        writer.write(partial_response)
        writer.write_eof()
        await writer.drain()

    server = await asyncio.start_server(client_connected, host=hostname, port=port)
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    response_bytes = await protocol._stream_reader.readline_with_timeout(timeout=1.0)

    assert response_bytes == partial_response
    assert protocol._stream_writer._transport.is_closing()

    server.close()
    await server.wait_closed()

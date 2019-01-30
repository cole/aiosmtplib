"""
Protocol level tests.
"""
import asyncio

import pytest

from aiosmtplib import SMTPResponseException, SMTPServerDisconnected, SMTPTimeoutError
from aiosmtplib.protocol import SMTPProtocol


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


class EchoServerProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self.transport.write(data)


@pytest.fixture(scope="function")
def echo_server(request, hostname, port, event_loop):
    server = event_loop.run_until_complete(
        event_loop.create_server(EchoServerProtocol, host=hostname, port=port)
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)


@pytest.fixture(scope="function")
def stream_reader(request, event_loop):
    return asyncio.StreamReader(limit=128, loop=event_loop)


async def test_protocol_connect(echo_server, stream_reader, event_loop, hostname, port):
    connect_future = event_loop.create_connection(
        lambda: SMTPProtocol(stream_reader, loop=event_loop), host=hostname, port=port
    )
    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0, loop=event_loop)

    assert isinstance(protocol._stream_reader, asyncio.StreamReader)
    assert isinstance(protocol._stream_writer, asyncio.StreamWriter)
    assert protocol._stream_reader._transport is not None
    assert not protocol._stream_reader._transport.is_closing()

    protocol._stream_writer.close()


async def test_protocol_read_limit_overrun(stream_reader, event_loop, hostname, port):
    async def client_connected(reader, writer):
        await reader.read(1000)
        long_response = (
            b"220 At vero eos et accusamus et iusto odio dignissimos ducimus qui "
            b"blanditiis praesentium voluptatum deleniti atque corruptis qui "
            b"blanditiis praesentium voluptatum\n"
        )
        writer.write(long_response)
        await writer.drain()

    server = await asyncio.start_server(
        client_connected, loop=event_loop, host=hostname, port=port
    )
    connect_future = event_loop.create_connection(
        lambda: SMTPProtocol(stream_reader, loop=event_loop), host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0, loop=event_loop)

    with pytest.raises(SMTPResponseException) as exc_info:
        await protocol.execute_command(b"TEST\n", timeout=1.0)

    assert exc_info.value.code == 500
    assert "Line too long" in exc_info.value.message

    server.close()
    await server.wait_closed()


async def test_protocol_connected_check_on_read_response(stream_reader, event_loop):
    smtp_protocol = SMTPProtocol(stream_reader, loop=event_loop)
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.read_response(timeout=1.0)


async def test_protocol_connected_check_on_write_and_drain(stream_reader, event_loop):
    smtp_protocol = SMTPProtocol(stream_reader, loop=event_loop)
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.write_and_drain(b"foo", timeout=1.0)


async def test_protocol_reader_connected_check_on_upgrade_transport(
    stream_reader, event_loop, client_tls_context
):
    smtp_protocol = SMTPProtocol(stream_reader, loop=event_loop)
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.upgrade_transport(client_tls_context)


async def test_protocol_writer_connected_check_on_upgrade_transport(
    stream_reader, event_loop, client_tls_context
):
    smtp_protocol = SMTPProtocol(stream_reader, loop=event_loop)

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.upgrade_transport(client_tls_context)


async def test_protocol_reader_connected_check_on_starttls(
    stream_reader, event_loop, client_tls_context
):
    smtp_protocol = SMTPProtocol(stream_reader, loop=event_loop)
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.starttls(client_tls_context, timeout=1.0)


async def test_protocol_writer_connected_check_on_starttls(
    stream_reader, event_loop, client_tls_context
):
    smtp_protocol = SMTPProtocol(stream_reader, loop=event_loop)

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.starttls(client_tls_context)


async def test_protocol_connected_check_on_drain_writer(stream_reader, event_loop):
    smtp_protocol = SMTPProtocol(stream_reader, loop=event_loop)

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol._drain_writer(timeout=1.0)


async def test_protocol_reader_connected_check_on_connection_made(
    stream_reader, event_loop
):
    smtp_protocol = SMTPProtocol(stream_reader, loop=event_loop)
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.connection_made(None)


async def test_protocol_reader_connected_check_on_readline(stream_reader, event_loop):
    smtp_protocol = SMTPProtocol(stream_reader, loop=event_loop)
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol._readline(timeout=1.0)


async def test_protocol_writer_connected_check_on_readline(stream_reader, event_loop):
    smtp_protocol = SMTPProtocol(stream_reader, loop=event_loop)
    smtp_protocol._stream_writer = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol._readline(timeout=1.0)


async def test_protocol_timeout_on_starttls(
    stream_reader, event_loop, hostname, port, client_tls_context
):
    async def client_connected(reader, writer):
        await reader.read(1000)
        writer.write(b"220 go ahead\n")
        await writer.drain()
        await asyncio.sleep(1.0, loop=event_loop)

    server = await asyncio.start_server(
        client_connected, loop=event_loop, host=hostname, port=port
    )
    connect_future = event_loop.create_connection(
        lambda: SMTPProtocol(stream_reader, loop=event_loop), host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0, loop=event_loop)

    with pytest.raises(SMTPTimeoutError):
        await protocol.starttls(client_tls_context, timeout=0.01)

    server.close()
    await server.wait_closed()


async def test_protocol_timeout_on_drain_writer(
    stream_reader, echo_server, event_loop, hostname, port
):
    connect_future = event_loop.create_connection(
        lambda: SMTPProtocol(stream_reader, loop=event_loop), host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0, loop=event_loop)

    protocol.pause_writing()
    protocol._stream_writer.write(b"1234")

    with pytest.raises(SMTPTimeoutError):
        await protocol._drain_writer(timeout=0.01)

    protocol._stream_writer.close()


async def test_connectionerror_on_drain_writer(
    stream_reader, echo_server, event_loop, hostname, port
):
    connect_future = event_loop.create_connection(
        lambda: SMTPProtocol(stream_reader, loop=event_loop), host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0, loop=event_loop)

    protocol.pause_writing()
    protocol._stream_reader._transport.close()

    with pytest.raises(ConnectionError):
        await protocol._drain_writer(timeout=1.0)


async def test_incompletereaderror_on_readline_with_partial_line(
    stream_reader, event_loop, hostname, port
):
    partial_response = b"499 incomplete response\\"

    async def client_connected(reader, writer):
        writer.write(partial_response)
        writer.write_eof()
        await writer.drain()

    server = await asyncio.start_server(
        client_connected, loop=event_loop, host=hostname, port=port
    )
    connect_future = event_loop.create_connection(
        lambda: SMTPProtocol(stream_reader, loop=event_loop), host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0, loop=event_loop)

    response_bytes = await protocol._readline(timeout=1.0)

    assert response_bytes == partial_response
    assert protocol._stream_writer._transport.is_closing()

    server.close()
    await server.wait_closed()

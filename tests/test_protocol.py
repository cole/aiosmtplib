"""
Protocol level tests.
"""
import asyncio

import pytest

from aiosmtplib import SMTPResponseException, SMTPServerDisconnected, SMTPTimeoutError
from aiosmtplib.protocol import SMTPProtocol


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def handle_dummy_client(reader, writer):
    while True:
        await reader.read(1000)


@pytest.fixture(scope="function")
def stream_reader(event_loop):
    return asyncio.StreamReader(limit=128, loop=event_loop)


@pytest.fixture(scope="function")
def smtp_protocol(request, event_loop, stream_reader):
    return SMTPProtocol(stream_reader, loop=event_loop)


@pytest.fixture(scope="function")
def dummy_server(request, hostname, port, event_loop):
    server = event_loop.run_until_complete(
        event_loop.create_server(handle_dummy_client, host=hostname, port=port)
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)


@pytest.fixture(scope="function")
async def dummy_smtp_protocol(
    request, smtp_protocol, dummy_server, event_loop, hostname, port
):
    connect_future = event_loop.create_connection(
        lambda: smtp_protocol, host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=0.01, loop=event_loop)

    request.addfinalizer(protocol._stream_writer.close)

    return protocol


async def test_protocol_connect(dummy_smtp_protocol):
    assert isinstance(dummy_smtp_protocol._stream_reader, asyncio.StreamReader)
    assert isinstance(dummy_smtp_protocol._stream_writer, asyncio.StreamWriter)


async def test_protocol_read_limit_overrun(smtp_protocol, event_loop, hostname, port):
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
        lambda: smtp_protocol, host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=0.01, loop=event_loop)

    with pytest.raises(SMTPResponseException) as exc_info:
        await protocol.execute_command(b"TEST\n", timeout=1)

    assert exc_info.value.code == 500
    assert "Line too long" in exc_info.value.message

    server.close()
    await server.wait_closed()


async def test_protocol_connected_check_on_read_response(smtp_protocol):
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.read_response(timeout=0.1)


async def test_protocol_connected_check_on_write_and_drain(smtp_protocol):
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.write_and_drain(b"foo", timeout=0.1)


async def test_protocol_reader_connected_check_on_upgrade_transport(
    smtp_protocol, client_tls_context
):
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.upgrade_transport(client_tls_context)


async def test_protocol_writer_connected_check_on_upgrade_transport(
    smtp_protocol, client_tls_context
):
    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.upgrade_transport(client_tls_context)


async def test_protocol_reader_connected_check_on_starttls(
    smtp_protocol, client_tls_context
):
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.starttls(client_tls_context)


async def test_protocol_writer_connected_check_on_starttls(
    smtp_protocol, client_tls_context
):
    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.starttls(client_tls_context)


async def test_protocol_connected_check_on_drain_writer(smtp_protocol):
    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol._drain_writer(timeout=0.1)


async def test_protocol_reader_connected_check_on_connection_made(smtp_protocol):
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.connection_made(None)


async def test_protocol_reader_connected_check_on_readline(smtp_protocol):
    smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol._readline(timeout=0.1)


async def test_protocol_writer_connected_check_on_readline(smtp_protocol):
    smtp_protocol._stream_writer = None

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol._readline(timeout=0.1)


async def test_protocol_timeout_on_starttls(
    smtp_protocol, event_loop, hostname, port, client_tls_context
):
    async def client_connected(reader, writer):
        await reader.read(1000)
        writer.write(b"220 go ahead\n")
        await writer.drain()
        await asyncio.sleep(0.2, loop=event_loop)

    server = await asyncio.start_server(
        client_connected, loop=event_loop, host=hostname, port=port
    )

    connect_future = event_loop.create_connection(
        lambda: smtp_protocol, host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=0.01, loop=event_loop)

    with pytest.raises(SMTPTimeoutError):
        await protocol.starttls(client_tls_context, timeout=0.01)

    server.close()
    await server.wait_closed()


async def test_protocol_timeout_on_drain_writer(dummy_smtp_protocol):
    dummy_smtp_protocol.pause_writing()
    dummy_smtp_protocol._stream_writer.write(b"1234")

    with pytest.raises(SMTPTimeoutError):
        await dummy_smtp_protocol._drain_writer(timeout=0.01)


async def test_connectionerror_on_drain_writer(dummy_smtp_protocol):
    dummy_smtp_protocol.pause_writing()
    dummy_smtp_protocol._stream_reader._transport.close()

    with pytest.raises(ConnectionError):
        await dummy_smtp_protocol._drain_writer(timeout=0.01)


async def test_connectionerror_on_readline(dummy_smtp_protocol):
    dummy_smtp_protocol._stream_reader._transport.close()

    with pytest.raises(ConnectionError):
        await dummy_smtp_protocol._readline(timeout=0.01)

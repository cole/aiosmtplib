"""
Protocol level tests.
"""
import asyncio
import ssl

import pytest

from aiosmtplib import SMTPResponseException, SMTPServerDisconnected, SMTPTimeoutError
from aiosmtplib.protocol import SMTPProtocol
from testserver import PresetServer


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


@pytest.fixture(scope="module")
def tls_context(request):
    return ssl.create_default_context(ssl.Purpose.SERVER_AUTH)


@pytest.fixture()
def raw_preset_server(request, event_loop, unused_tcp_port):
    server = PresetServer("localhost", unused_tcp_port, loop=event_loop)

    event_loop.run_until_complete(server.start())

    def close_server():
        event_loop.run_until_complete(server.stop())

    request.addfinalizer(close_server)

    return server


@pytest.fixture()
async def smtp_protocol(request, raw_preset_server, event_loop):
    reader = asyncio.StreamReader(limit=128, loop=event_loop)
    protocol = SMTPProtocol(reader, loop=event_loop)
    connect_future = event_loop.create_connection(
        lambda: protocol, host=raw_preset_server.hostname, port=raw_preset_server.port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1, loop=event_loop)

    return protocol


@pytest.fixture()
def disconnected_smtp_protocol(request, event_loop):
    reader = asyncio.StreamReader(limit=128, loop=event_loop)
    return SMTPProtocol(reader, loop=event_loop)


async def test_protocol_connect(smtp_protocol):
    assert isinstance(smtp_protocol._stream_reader, asyncio.StreamReader)
    assert isinstance(smtp_protocol._stream_writer, asyncio.StreamWriter)


async def test_protocol_read_limit_overrun(smtp_protocol, raw_preset_server):
    long_response = (
        b"220 At vero eos et accusamus et iusto odio dignissimos ducimus qui "
        b"blanditiis praesentium voluptatum deleniti atque corruptis qui "
        b"blanditiis praesentium voluptatum\n"
    )
    raw_preset_server.responses.append(long_response)

    with pytest.raises(SMTPResponseException) as exc_info:
        await smtp_protocol.execute_command(b"TEST\n", timeout=1)

    assert exc_info.value.code == 500
    assert "Line too long" in exc_info.value.message


async def test_protocol_connected_check_on_read_response(disconnected_smtp_protocol):
    disconnected_smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await disconnected_smtp_protocol.read_response(timeout=1)


async def test_protocol_connected_check_on_write_and_drain(disconnected_smtp_protocol):
    with pytest.raises(SMTPServerDisconnected):
        await disconnected_smtp_protocol.write_and_drain(b"foo", timeout=1)


async def test_protocol_reader_connected_check_on_upgrade_transport(
    disconnected_smtp_protocol, tls_context
):
    disconnected_smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await disconnected_smtp_protocol.upgrade_transport(tls_context)


async def test_protocol_writer_connected_check_on_upgrade_transport(
    disconnected_smtp_protocol, tls_context
):
    with pytest.raises(SMTPServerDisconnected):
        await disconnected_smtp_protocol.upgrade_transport(tls_context)


async def test_protocol_reader_connected_check_on_starttls(
    disconnected_smtp_protocol, tls_context
):
    disconnected_smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await disconnected_smtp_protocol.starttls(tls_context)


async def test_protocol_writer_connected_check_on_starttls(
    disconnected_smtp_protocol, tls_context
):
    with pytest.raises(SMTPServerDisconnected):
        await disconnected_smtp_protocol.starttls(tls_context)


async def test_protocol_connected_check_on_drain_writer(disconnected_smtp_protocol):
    with pytest.raises(SMTPServerDisconnected):
        await disconnected_smtp_protocol._drain_writer(timeout=1)


async def test_protocol_reader_connected_check_on_connection_made(
    disconnected_smtp_protocol
):
    disconnected_smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await disconnected_smtp_protocol.connection_made(None)


async def test_protocol_reader_connected_check_on_readline(disconnected_smtp_protocol):
    disconnected_smtp_protocol._stream_reader = None

    with pytest.raises(SMTPServerDisconnected):
        await disconnected_smtp_protocol._readline(timeout=1)


async def test_protocol_writer_connected_check_on_readline(disconnected_smtp_protocol):
    disconnected_smtp_protocol._stream_writer = None

    with pytest.raises(SMTPServerDisconnected):
        await disconnected_smtp_protocol._readline(timeout=1)


async def test_protocol_timeout_on_starttls(
    smtp_protocol, raw_preset_server, tls_context
):
    raw_preset_server.responses.append(b"220 Go ahead\n")
    raw_preset_server.responses.append(b"unterminated line")

    with pytest.raises(SMTPTimeoutError):
        await smtp_protocol.starttls(tls_context, timeout=0.00000001)


async def test_protocol_timeout_on_drain_writer(smtp_protocol):
    smtp_protocol.pause_writing()
    smtp_protocol._stream_writer.write(b"1234")

    with pytest.raises(SMTPTimeoutError):
        await smtp_protocol._drain_writer(timeout=0.00000000000001)


async def test_connectionerror_on_drain_writer(smtp_protocol):
    smtp_protocol.pause_writing()
    smtp_protocol._stream_reader._transport.close()

    with pytest.raises(ConnectionError):
        await smtp_protocol._drain_writer(timeout=1)


async def test_connectionerror_on_readline(smtp_protocol):
    smtp_protocol._stream_reader._transport.close()

    with pytest.raises(ConnectionError):
        await smtp_protocol._readline(timeout=1)

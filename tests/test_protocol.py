"""
Protocol level tests.
"""
import asyncio
import time

import pytest

from aiosmtplib import SMTPResponseException, SMTPServerDisconnected, SMTPTimeoutError
from aiosmtplib.protocol import SMTPProtocol


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


class DummyProtocol(asyncio.Protocol):
    """
    Server protocol for monkeypatching in client protocol tests.
    """

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self.transport.close()


@pytest.fixture(scope="function")
def stream_reader(event_loop):
    return asyncio.StreamReader(limit=128, loop=event_loop)


@pytest.fixture(scope="function")
def smtp_protocol(request, event_loop, stream_reader):
    return SMTPProtocol(stream_reader, loop=event_loop)


@pytest.fixture(scope="function")
def dummy_server(request, hostname, port, event_loop):
    server = event_loop.run_until_complete(
        event_loop.create_server(lambda: DummyProtocol(), host=hostname, port=port)
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)


@pytest.fixture(scope="function")
async def connected_smtp_protocol(
    request, smtp_protocol, dummy_server, event_loop, hostname, port
):
    connect_future = event_loop.create_connection(
        lambda: smtp_protocol, host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=0.01, loop=event_loop)

    request.addfinalizer(protocol._stream_writer.close)

    return protocol


async def test_protocol_connect(connected_smtp_protocol):
    assert isinstance(connected_smtp_protocol._stream_reader, asyncio.StreamReader)
    assert isinstance(connected_smtp_protocol._stream_writer, asyncio.StreamWriter)


async def test_protocol_read_limit_overrun(
    connected_smtp_protocol, dummy_server, monkeypatch
):
    def write_response(self, data):
        long_response = (
            b"220 At vero eos et accusamus et iusto odio dignissimos ducimus qui "
            b"blanditiis praesentium voluptatum deleniti atque corruptis qui "
            b"blanditiis praesentium voluptatum\n"
        )
        self.transport.write(long_response)

    monkeypatch.setattr(DummyProtocol, "data_received", write_response)

    with pytest.raises(SMTPResponseException) as exc_info:
        await connected_smtp_protocol.execute_command(b"TEST\n", timeout=1)

    assert exc_info.value.code == 500
    assert "Line too long" in exc_info.value.message


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
    connected_smtp_protocol, dummy_server, event_loop, client_tls_context, monkeypatch
):
    def write_response(self, data):
        if not hasattr(self, "_responded"):
            self.transport.write(b"220 go ahead\n")
            self._responded = True
        else:
            time.sleep(0.02)  # TODO - use async sleep here

    monkeypatch.setattr(DummyProtocol, "data_received", write_response)

    with pytest.raises(SMTPTimeoutError):
        await connected_smtp_protocol.starttls(client_tls_context, timeout=0.01)


async def test_protocol_timeout_on_drain_writer(connected_smtp_protocol):
    connected_smtp_protocol.pause_writing()
    connected_smtp_protocol._stream_writer.write(b"1234")

    with pytest.raises(SMTPTimeoutError):
        await connected_smtp_protocol._drain_writer(timeout=0.01)


async def test_connectionerror_on_drain_writer(connected_smtp_protocol):
    connected_smtp_protocol.pause_writing()
    connected_smtp_protocol._stream_reader._transport.close()

    with pytest.raises(ConnectionError):
        await connected_smtp_protocol._drain_writer(timeout=0.01)


async def test_connectionerror_on_readline(connected_smtp_protocol):
    connected_smtp_protocol._stream_reader._transport.close()

    with pytest.raises(ConnectionError):
        await connected_smtp_protocol._readline(timeout=0.01)

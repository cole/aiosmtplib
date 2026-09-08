"""
Protocol level tests.
"""

import asyncio
import gc
import os
import socket
import ssl

import pytest

from aiosmtplib import SMTPResponseException, SMTPServerDisconnected, SMTPTimeoutError
from aiosmtplib.protocol import (
    DATA_CHUNK_SIZE,
    FlowControlMixin,
    SMTPProtocol,
    _set_timeout,
)

from .conftest import ConnectProtocol


async def test_protocol_connect(hostname: str, echo_server_port: int) -> None:
    event_loop = asyncio.get_running_loop()
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=echo_server_port
    )
    transport, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    assert getattr(protocol, "transport", None) is transport
    assert not transport.is_closing()

    transport.close()


async def test_protocol_read_limit_overrun(
    connect_protocol: ConnectProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1000)
        long_response = (
            b"220 At vero eos et accusamus et iusto odio dignissimos ducimus qui "
            b"blanditiis praesentium voluptatum deleniti atque corruptis qui "
            b"blanditiis praesentium voluptatum\n"
        )
        writer.write(long_response)
        await writer.drain()

    protocol = await connect_protocol(client_connected)
    monkeypatch.setattr("aiosmtplib.protocol.MAX_LINE_LENGTH", 128)

    with pytest.raises(SMTPResponseException) as exc_info:
        await protocol.execute_command(b"TEST", timeout=1.0)

    assert exc_info.value.code == -1
    assert "Response too long" in exc_info.value.message


async def test_protocol_response_no_newline_overrun(
    connect_protocol: ConnectProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1000)
        # No line ending at all, so the per-line cap is never reached.
        writer.write(b"2" * 500)
        await writer.drain()

    protocol = await connect_protocol(client_connected)
    monkeypatch.setattr("aiosmtplib.protocol.MAX_RESPONSE_LENGTH", 128)

    with pytest.raises(SMTPResponseException) as exc_info:
        await protocol.execute_command(b"TEST", timeout=1.0)

    assert exc_info.value.code == -1
    assert "Response too long" in exc_info.value.message


async def test_protocol_response_continuation_overrun(
    connect_protocol: ConnectProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1000)
        # Endless multiline continuation; each line is well under the per-line
        # cap, so only the total response cap can stop it.
        writer.write(b"250-spam\r\n" * 100)
        await writer.drain()

    protocol = await connect_protocol(client_connected)
    monkeypatch.setattr("aiosmtplib.protocol.MAX_RESPONSE_LENGTH", 128)

    with pytest.raises(SMTPResponseException) as exc_info:
        await protocol.execute_command(b"TEST", timeout=1.0)

    assert exc_info.value.code == -1
    assert "Response too long" in exc_info.value.message


async def test_protocol_connected_check_on_read_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = SMTPProtocol()
    monkeypatch.setattr(protocol, "transport", None)

    with pytest.raises(SMTPServerDisconnected):
        await protocol.read_response(timeout=1.0)


async def test_protocol_read_only_transport_error() -> None:
    event_loop = asyncio.get_running_loop()
    read_descriptor, _ = os.pipe()
    read_pipe = os.fdopen(read_descriptor, "rb", buffering=0)
    connect_future = event_loop.connect_read_pipe(SMTPProtocol, read_pipe)
    transport, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    assert getattr(protocol, "transport", None) is transport

    with pytest.raises(RuntimeError, match="does not support writing"):
        protocol.write(b"TEST\n")

    transport.close()


async def test_protocol_connected_check_on_start_tls(
    client_tls_context: ssl.SSLContext,
) -> None:
    smtp_protocol = SMTPProtocol()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.start_tls(client_tls_context, timeout=1.0)


async def test_protocol_already_over_tls_check_on_start_tls(
    client_tls_context: ssl.SSLContext,
) -> None:
    smtp_protocol = SMTPProtocol()
    smtp_protocol._over_ssl = True

    with pytest.raises(RuntimeError, match="Already using TLS"):
        await smtp_protocol.start_tls(client_tls_context)


async def test_protocol_connection_reset_on_starttls(
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
        raise ConnectionResetError("Connection was reset")

    monkeypatch.setattr(event_loop, "start_tls", mock_start_tls)

    with pytest.raises(SMTPServerDisconnected):
        await protocol.start_tls(client_tls_context)

    transport.close()


async def test_protocol_timeout_on_starttls(
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
        raise TimeoutError("Timed out")

    monkeypatch.setattr(event_loop, "start_tls", mock_start_tls)

    with pytest.raises(SMTPTimeoutError, match="Timed out while upgrading transport"):
        await protocol.start_tls(client_tls_context)

    transport.close()


async def test_protocol_discards_buffer_before_tls_handshake(
    connect_protocol: ConnectProtocol,
    client_tls_context: ssl.SSLContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Bytes a MITM injects after the 220 STARTTLS reply must not survive into the
    encrypted session.
    """

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.readuntil(b"\r\n")
        # 220 reply plus injected plaintext, in a single segment.
        writer.write(b"220 Go ahead\r\n250-mx.evil\r\n250 AUTH LOGIN\r\n")
        await writer.drain()
        await reader.read()  # keep the connection open through start_tls

    protocol = await connect_protocol(client_connected)

    captured: dict[str, bytes] = {}

    async def mock_start_tls(transport, proto, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["buffer"] = bytes(proto._buffer)
        return transport

    monkeypatch.setattr(asyncio.get_running_loop(), "start_tls", mock_start_tls)

    response = await protocol.start_tls(client_tls_context, timeout=1.0)

    assert response.code == 220
    assert captured["buffer"] == b""


async def test_error_on_readline_with_partial_line(
    connect_protocol: ConnectProtocol,
) -> None:
    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writer.write(b"499 incomplete response\\")
        writer.write_eof()
        await writer.drain()

    protocol = await connect_protocol(client_connected)

    with pytest.raises(SMTPServerDisconnected):
        await protocol.read_response(timeout=1.0)


async def test_protocol_error_on_readline_with_malformed_response(
    connect_protocol: ConnectProtocol,
) -> None:
    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writer.write(b"ERROR\n")
        writer.write_eof()
        await writer.drain()

    protocol = await connect_protocol(client_connected)

    with pytest.raises(
        SMTPResponseException, match="Malformed SMTP response line: ERROR"
    ):
        await protocol.read_response(timeout=1.0)


async def test_protocol_response_waiter_unset(
    connect_protocol: ConnectProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1000)
        writer.write(b"220 Hi\r\n")
        await writer.drain()

    protocol = await connect_protocol(client_connected)
    monkeypatch.setattr(protocol, "_response_waiter", None)

    with pytest.raises(SMTPServerDisconnected):
        await protocol.execute_command(b"TEST", timeout=1.0)


async def test_protocol_data_received_called_twice(
    connect_protocol: ConnectProtocol,
) -> None:
    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1000)
        writer.write(b"220 Hi\r\n")
        await writer.drain()
        await asyncio.sleep(0)
        writer.write(b"221 Hi again!\r\n")
        await writer.drain()

    protocol = await connect_protocol(client_connected)

    response = await protocol.execute_command(b"TEST", timeout=1.0)

    assert response.code == 220
    assert response.message == "Hi"


@pytest.mark.skip_if_uvloop(reason="flaky on uvloop")
async def test_protocol_exception_cleanup_warning(
    caplog: pytest.LogCaptureFixture,
    debug_event_loop: asyncio.AbstractEventLoop,
    connect_protocol: ConnectProtocol,
) -> None:
    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1000)
        writer.write(b"220 Hi\r\n")
        await writer.drain()

        await reader.read(1000)
        writer.write(b"221 Bye\r\n")
        await writer.drain()

        writer.transport.close()

    protocol = await connect_protocol(client_connected)

    await protocol.execute_command(b"HELO", timeout=1.0)
    await protocol.execute_command(b"QUIT", timeout=1.0)

    del protocol
    # Force garbage collection
    gc.collect()

    assert "Future exception was never retrieved" not in caplog.text


async def test_protocol_missing_command_lock_disconnected() -> None:
    event_loop = asyncio.get_running_loop()
    protocol = SMTPProtocol(event_loop)

    with pytest.raises(SMTPServerDisconnected):
        await protocol.execute_command(b"TEST")

    with pytest.raises(SMTPServerDisconnected):
        await protocol.execute_data_command(b"TEST\n")


async def test_flow_control_mixin_drain() -> None:
    event_loop = asyncio.get_running_loop()

    # Adapted from stdlib
    drained = 0

    async def drainer(stream) -> None:
        nonlocal drained
        await stream._drain_helper()
        drained += 1

    stream = FlowControlMixin(event_loop)
    stream.pause_writing()
    event_loop.call_later(0.1, stream.resume_writing)
    await asyncio.gather(*[drainer(stream) for _ in range(10)])
    assert drained == 10


async def test_flow_control_mixin_drain_incomplete() -> None:
    event_loop = asyncio.get_running_loop()

    flow_control = FlowControlMixin(event_loop)
    flow_control.pause_writing()

    waiter = event_loop.create_future()
    flow_control._drain_waiters.append(waiter)

    waiter.set_result("test")
    flow_control.resume_writing()

    assert waiter.done()
    assert not waiter.cancelled()


async def test_flow_control_mixin_connection_lost_exception() -> None:
    event_loop = asyncio.get_running_loop()

    flow_control = FlowControlMixin(event_loop)
    flow_control.pause_writing()
    waiter = event_loop.create_future()

    flow_control._drain_waiters.append(waiter)

    exc = ConnectionAbortedError("boom")
    flow_control.connection_lost(exc)

    assert waiter.done()
    assert not waiter.cancelled()
    assert waiter.exception() is exc


async def test_flow_control_mixin_connection_lost_no_exception() -> None:
    event_loop = asyncio.get_running_loop()

    flow_control = FlowControlMixin(event_loop)
    flow_control.pause_writing()
    waiter = event_loop.create_future()

    flow_control._drain_waiters.append(waiter)

    flow_control.connection_lost(None)

    assert waiter.done()
    assert not waiter.cancelled()
    assert waiter.exception() is None


async def test_flow_control_mixin_connection_lost_done() -> None:
    event_loop = asyncio.get_running_loop()

    flow_control = FlowControlMixin(event_loop)
    flow_control.pause_writing()
    waiter = event_loop.create_future()

    flow_control._drain_waiters.append(waiter)
    exc = ConnectionResetError("boom")
    waiter.set_exception(exc)

    flow_control.connection_lost(None)

    assert waiter.done()
    assert not waiter.cancelled()
    assert waiter.exception() is exc


async def test_flow_control_mixin_drain_helper() -> None:
    loop = asyncio.get_running_loop()
    flow_control = FlowControlMixin(loop)

    await flow_control._drain_helper()


async def test_flow_control_mixin_drain_helper_connection_lost() -> None:
    loop = asyncio.get_running_loop()
    flow_control = FlowControlMixin(loop)
    flow_control.pause_writing()
    flow_control.connection_lost(None)

    with pytest.raises(ConnectionResetError):
        await flow_control._drain_helper()


class _FakeTransport(asyncio.Transport):
    """Minimal transport stub for driving SMTPProtocol callbacks directly."""

    def __init__(self) -> None:
        super().__init__()
        self._extra: dict[str, object] = {"sslcontext": object()}

    def get_extra_info(self, name: str, default: object = None) -> object:
        return self._extra.get(name, default)

    def is_closing(self) -> bool:
        return False


async def test_protocol_connection_lost_after_quit_resolves_waiter() -> None:
    """
    Regression test for https://github.com/cole/aiosmtplib/issues/345.

    When the peer drops the transport with an exception after ``QUIT\\r\\n``
    has been written but before the 221 reply is parsed (e.g. AWS SES closes
    TLS without ``close_notify``, surfaced as ``connection_lost(SSLEOFError)``),
    the response waiter must be resolved so that ``SMTP.quit()`` returns
    promptly instead of blocking until the read timeout.
    """
    protocol = SMTPProtocol()
    protocol.connection_made(_FakeTransport())

    protocol._quit_sent = True
    waiter = protocol._response_waiter
    assert waiter is not None and not waiter.done()

    protocol.connection_lost(ssl.SSLEOFError("EOF occurred in violation of protocol"))

    assert waiter.done()
    assert waiter.exception() is None
    response = waiter.result()
    assert response.code == 221


async def test_protocol_connection_lost_without_quit_raises() -> None:
    """
    Without an outstanding QUIT, ``connection_lost`` must continue to
    surface ``SMTPServerDisconnected`` on the response waiter.
    """
    protocol = SMTPProtocol()
    protocol.connection_made(_FakeTransport())

    waiter = protocol._response_waiter
    assert waiter is not None and not waiter.done()

    protocol.connection_lost(ConnectionResetError("boom"))

    assert waiter.done()
    exc = waiter.exception()
    assert isinstance(exc, SMTPServerDisconnected)


async def test_protocol_close_waiter_resolves_on_connection_lost() -> None:
    """
    The future returned by _get_close_waiter (used by
    asyncio.StreamWriter.wait_closed) must resolve when the connection is
    lost, or wait_closed() hangs forever.
    """
    protocol = SMTPProtocol()
    protocol.connection_made(_FakeTransport())
    close_waiter = protocol._get_close_waiter(None)  # type: ignore[arg-type]
    assert not close_waiter.done()

    protocol.connection_lost(None)

    assert close_waiter.done()
    assert close_waiter.exception() is None


async def test_protocol_close_waiter_raises_on_connection_lost_error() -> None:
    protocol = SMTPProtocol()
    protocol.connection_made(_FakeTransport())
    close_waiter = protocol._get_close_waiter(None)  # type: ignore[arg-type]

    exc = ConnectionResetError("boom")
    protocol.connection_lost(exc)

    assert close_waiter.done()
    assert close_waiter.exception() is exc


async def test_protocol_stream_writer_wait_closed(
    hostname: str, echo_server_port: int
) -> None:
    event_loop = asyncio.get_running_loop()
    transport, protocol = await event_loop.create_connection(
        SMTPProtocol, host=hostname, port=echo_server_port
    )
    writer = asyncio.StreamWriter(transport, protocol, None, event_loop)  # type: ignore[arg-type]

    writer.close()
    await asyncio.wait_for(writer.wait_closed(), timeout=1.0)

    assert not protocol.is_connected


class _WriteRecordingTransport(_FakeTransport):
    def __init__(self) -> None:
        super().__init__()
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def close(self) -> None:
        self.closed = True

    def is_closing(self) -> bool:
        return self.closed


@pytest.mark.parametrize(
    "arg",
    (
        b"FROM:<a@b.com\r\nRCPT TO:<hijacker@example.com>",
        b"FROM:<a@b.com\rRCPT TO:<hijacker@example.com>",
        b"FROM:<a@b.com\nRCPT TO:<hijacker@example.com>",
        b"FROM:<a@b.com\x00>",
        b"FROM:<a@b.com\tEVIL>",
        b"FROM:<a@b.com\x7f>",
    ),
    ids=("crlf", "cr", "lf", "nul", "tab", "del"),
)
async def test_protocol_execute_command_rejects_injected_args(arg: bytes) -> None:
    protocol = SMTPProtocol()
    transport = _WriteRecordingTransport()
    protocol.connection_made(transport)

    with pytest.raises(ValueError, match="prohibited"):
        await protocol.execute_command(b"MAIL", arg, timeout=1.0)

    assert transport.writes == []


async def test_protocol_execute_command_rejects_injected_option() -> None:
    protocol = SMTPProtocol()
    transport = _WriteRecordingTransport()
    protocol.connection_made(transport)

    with pytest.raises(ValueError, match="prohibited"):
        await protocol.execute_command(
            b"MAIL", b"FROM:<a@b.com>", b"BODY=8BITMIME\r\nDATA", timeout=1.0
        )

    assert transport.writes == []


async def test_protocol_ignores_unsolicited_data_between_commands() -> None:
    """
    Data received while no command is outstanding must be discarded, not stored
    on the next waiter. Otherwise a single unsolicited line permanently desyncs
    every subsequent command/response pair by one.
    """
    protocol = SMTPProtocol()
    transport = _WriteRecordingTransport()
    protocol.connection_made(transport)

    # Greeting, consumed by a normal read.
    protocol.data_received(b"220 hi\r\n")
    greeting = await protocol.read_response(timeout=1.0)
    assert greeting.code == 220

    # An unsolicited line arrives while the client is idle between commands.
    protocol.data_received(b"250 unsolicited\r\n")
    assert protocol._response_waiter is not None
    assert not protocol._response_waiter.done()
    assert protocol._buffer == bytearray()

    # The next command must receive its OWN response, not the stale line.
    task = asyncio.ensure_future(protocol.execute_command(b"NOOP", timeout=1.0))
    await asyncio.sleep(0)  # let the command write and start awaiting
    protocol.data_received(b"250 real noop reply\r\n")

    response = await task
    assert response.code == 250
    assert response.message == "real noop reply"


async def test_protocol_ignores_unsolicited_multiline_data() -> None:
    """An unsolicited multiline response between commands must be discarded."""
    protocol = SMTPProtocol()
    transport = _WriteRecordingTransport()
    protocol.connection_made(transport)

    protocol.data_received(b"220 hi\r\n")
    greeting = await protocol.read_response(timeout=1.0)
    assert greeting.code == 220

    # A full multiline response arrives while no command is outstanding.
    protocol.data_received(b"250-foo\r\n250-bar\r\n250 baz\r\n")
    assert protocol._response_waiter is not None
    assert not protocol._response_waiter.done()
    assert protocol._buffer == bytearray()

    task = asyncio.ensure_future(protocol.execute_command(b"NOOP", timeout=1.0))
    await asyncio.sleep(0)
    protocol.data_received(b"250 real\r\n")

    response = await task
    assert response.code == 250
    assert response.message == "real"


async def test_protocol_ignores_unsolicited_partial_data() -> None:
    """
    Unsolicited data fragmented across data_received calls between commands
    must be discarded, not buffered for the next command.
    """
    protocol = SMTPProtocol()
    transport = _WriteRecordingTransport()
    protocol.connection_made(transport)

    protocol.data_received(b"220 hi\r\n")
    greeting = await protocol.read_response(timeout=1.0)
    assert greeting.code == 220

    # Unsolicited response trickling in across multiple chunks, including a
    # mid-line split, while no command is outstanding.
    protocol.data_received(b"250-foo\r\n")
    protocol.data_received(b"250 ba")
    protocol.data_received(b"r\r\n")
    assert protocol._response_waiter is not None
    assert not protocol._response_waiter.done()
    assert protocol._buffer == bytearray()

    task = asyncio.ensure_future(protocol.execute_command(b"NOOP", timeout=1.0))
    await asyncio.sleep(0)
    protocol.data_received(b"250 real\r\n")

    response = await task
    assert response.code == 250
    assert response.message == "real"


async def test_protocol_data_received_without_response_waiter() -> None:
    """
    Data can arrive after the connection is lost but before cleanup
    (e.g. a queued data_received callback); it should be dropped, not raise.
    """
    protocol = SMTPProtocol(loop=asyncio.get_running_loop())
    assert protocol._response_waiter is None

    protocol.data_received(b"421 Going away\r\n")

    assert not protocol._buffer


async def test_protocol_malformed_response_closes_connection(
    connect_protocol: ConnectProtocol,
) -> None:
    """
    A reply we cannot parse means we no longer know where the next reply
    starts, so the connection must be dropped rather than left desynced with
    the bad bytes still buffered.
    """

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.readline()
        writer.write(b"ERROR\r\n250 ok\r\n")
        await writer.drain()
        await reader.read(1000)

    protocol = await connect_protocol(client_connected)

    with pytest.raises(SMTPResponseException, match="Malformed SMTP response line"):
        await protocol.execute_command(b"NOOP", timeout=1.0)

    assert not protocol.is_connected
    assert protocol._buffer == bytearray()

    with pytest.raises(SMTPServerDisconnected):
        await protocol.execute_command(b"NOOP", timeout=1.0)


async def test_protocol_response_overrun_closes_connection(
    connect_protocol: ConnectProtocol, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The rest of an oversized reply keeps arriving after the error is raised,
    and must not be paired with the next command.
    """

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.readline()
        writer.write(b"250-spam\r\n" * 100)
        await writer.drain()
        await reader.read(1000)

    protocol = await connect_protocol(client_connected)
    monkeypatch.setattr("aiosmtplib.protocol.MAX_RESPONSE_LENGTH", 128)

    with pytest.raises(SMTPResponseException, match="Response too long"):
        await protocol.execute_command(b"NOOP", timeout=1.0)

    assert not protocol.is_connected

    with pytest.raises(SMTPServerDisconnected):
        await protocol.execute_command(b"NOOP", timeout=1.0)


async def test_protocol_data_command_slow_reader(
    connect_protocol: ConnectProtocol,
) -> None:
    """
    The reply timeout must not start until the message has been handed off, so
    an upload that takes longer than the timeout but never stalls succeeds.
    """

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        sock = writer.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 64 * 1024)
        await reader.readline()
        writer.write(b"354 go\r\n")
        await writer.drain()
        while True:
            chunk = await reader.read(64 * 1024)
            if not chunk or chunk.endswith(b"\r\n.\r\n"):
                break
            await asyncio.sleep(0.01)
        writer.write(b"250 ok\r\n")
        await writer.drain()

    protocol = await connect_protocol(client_connected)
    # Keep kernel buffers small, so backpressure reflects what the server has
    # actually read rather than what the kernel has absorbed.
    assert protocol.transport is not None
    sock = protocol.transport.get_extra_info("socket")
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 64 * 1024)

    response = await protocol.execute_data_command(
        b"x" * (4 * 1024 * 1024), timeout=0.2
    )

    assert response.code == 250


class _PausingTransport(_WriteRecordingTransport):
    """Pauses the protocol after every message write, until resumed by hand."""

    def __init__(self, protocol: SMTPProtocol) -> None:
        super().__init__()
        self.protocol = protocol

    def write(self, data: bytes) -> None:
        super().write(data)
        if data != b"DATA\r\n":
            self.protocol.pause_writing()


async def test_protocol_data_command_waits_for_drain() -> None:
    protocol = SMTPProtocol()
    transport = _PausingTransport(protocol)
    protocol.connection_made(transport)

    message = b"x" * DATA_CHUNK_SIZE
    task = asyncio.ensure_future(protocol.execute_data_command(message, timeout=0.5))
    await asyncio.sleep(0)
    protocol.data_received(b"354 go\r\n")

    # Each chunk stalls for less than the timeout, but the upload as a whole
    # takes longer than it. Only inactivity should count.
    for expected_writes in (2, 3):
        await asyncio.sleep(0)
        assert len(transport.writes) == expected_writes
        await asyncio.sleep(0.3)
        assert not task.done()
        protocol.resume_writing()

    await asyncio.sleep(0)
    protocol.data_received(b"250 ok\r\n")

    response = await task
    assert response.code == 250
    assert b"".join(transport.writes[1:]) == message + b"\r\n.\r\n"


async def test_protocol_data_command_drain_timeout() -> None:
    protocol = SMTPProtocol()
    transport = _PausingTransport(protocol)
    protocol.connection_made(transport)

    task = asyncio.ensure_future(protocol.execute_data_command(b"hello", timeout=0.05))
    await asyncio.sleep(0)
    protocol.data_received(b"354 go\r\n")

    with pytest.raises(SMTPTimeoutError, match="sending message data"):
        await task


async def test_protocol_data_command_drain_connection_lost() -> None:
    protocol = SMTPProtocol()
    transport = _PausingTransport(protocol)
    protocol.connection_made(transport)

    task = asyncio.ensure_future(protocol.execute_data_command(b"hello", timeout=1.0))
    await asyncio.sleep(0)
    protocol.data_received(b"354 go\r\n")
    await asyncio.sleep(0)
    protocol.connection_lost(ConnectionResetError())

    with pytest.raises(SMTPServerDisconnected):
        await task


async def test_protocol_data_command_cancelled_during_drain() -> None:
    protocol = SMTPProtocol()
    transport = _PausingTransport(protocol)
    protocol.connection_made(transport)

    task = asyncio.ensure_future(protocol.execute_data_command(b"hello", timeout=1.0))
    await asyncio.sleep(0)
    protocol.data_received(b"354 go\r\n")
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert transport.closed


async def test_protocol_data_command_writes_in_chunks() -> None:
    protocol = SMTPProtocol()
    transport = _WriteRecordingTransport()
    protocol.connection_made(transport)

    message = b"x" * (DATA_CHUNK_SIZE * 2 + 1)
    task = asyncio.ensure_future(protocol.execute_data_command(message, timeout=1.0))
    await asyncio.sleep(0)
    protocol.data_received(b"354 go\r\n")
    await asyncio.sleep(0)
    protocol.data_received(b"250 ok\r\n")
    await task

    body = b"".join(transport.writes[1:])
    assert body == message + b"\r\n.\r\n"
    assert len(transport.writes) == 4
    assert all(len(chunk) <= DATA_CHUNK_SIZE for chunk in transport.writes[1:])


async def test_set_timeout_ignores_done_waiter() -> None:
    """
    The timeout callback can fire after the waiter has already been resolved,
    if both land in the same loop iteration; it must not touch the result.
    """
    waiter = asyncio.get_running_loop().create_future()
    waiter.set_result("done")

    _set_timeout(waiter)

    assert waiter.result() == "done"


async def test_protocol_malformed_response_on_closing_transport() -> None:
    """
    A bad reply arriving after the transport has already started closing
    still fails the waiter, without trying to close the transport again.
    """
    protocol = SMTPProtocol()
    transport = _WriteRecordingTransport()
    protocol.connection_made(transport)

    task = asyncio.ensure_future(protocol.execute_command(b"NOOP", timeout=1.0))
    await asyncio.sleep(0)
    transport.close()
    protocol.data_received(b"ERROR\r\n")

    with pytest.raises(SMTPResponseException, match="Malformed SMTP response line"):
        await task

    assert protocol._buffer == bytearray()


async def test_protocol_read_response_cancelled_after_connection_lost() -> None:
    """
    Cancellation delivered in the same loop iteration as connection_lost
    should propagate without trying to close the (already gone) transport.
    """
    protocol = SMTPProtocol()
    transport = _WriteRecordingTransport()
    protocol.connection_made(transport)

    task = asyncio.ensure_future(protocol.execute_command(b"NOOP", timeout=1.0))
    await asyncio.sleep(0)
    protocol.connection_lost(None)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert protocol.transport is None
    assert not transport.closed


async def test_protocol_data_command_cancelled_after_connection_lost() -> None:
    protocol = SMTPProtocol()
    transport = _PausingTransport(protocol)
    protocol.connection_made(transport)

    task = asyncio.ensure_future(protocol.execute_data_command(b"hello", timeout=1.0))
    await asyncio.sleep(0)
    protocol.data_received(b"354 go\r\n")
    await asyncio.sleep(0)
    protocol.connection_lost(None)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert protocol.transport is None
    assert not transport.closed


async def test_protocol_start_tls_transport_closing_after_reply(
    client_tls_context: ssl.SSLContext,
) -> None:
    protocol = SMTPProtocol()
    transport = _WriteRecordingTransport()
    transport._extra.clear()  # not already over TLS
    protocol.connection_made(transport)

    task = asyncio.ensure_future(protocol.start_tls(client_tls_context, timeout=1.0))
    await asyncio.sleep(0)
    transport.close()
    protocol.data_received(b"220 Go ahead\r\n")

    with pytest.raises(SMTPServerDisconnected, match="Connection lost"):
        await task

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
from aiosmtplib.protocol import FlowControlMixin, SMTPProtocol

from .compat import cleanup_server


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
    bind_address: str,
    hostname: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_loop = asyncio.get_running_loop()

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

    server = await asyncio.start_server(
        client_connected, host=bind_address, port=0, family=socket.AF_INET
    )
    server_port = server.sockets[0].getsockname()[1] if server.sockets else 0
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=server_port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    monkeypatch.setattr("aiosmtplib.protocol.MAX_LINE_LENGTH", 128)

    with pytest.raises(SMTPResponseException) as exc_info:
        await protocol.execute_command(b"TEST", timeout=1.0)  # type: ignore

    assert exc_info.value.code == -1
    assert "Response too long" in exc_info.value.message

    server.close()
    await cleanup_server(server)


async def test_protocol_response_no_newline_overrun(
    bind_address: str,
    hostname: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_loop = asyncio.get_running_loop()

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1000)
        # No line ending at all, so the per-line cap is never reached.
        writer.write(b"2" * 500)
        await writer.drain()

    server = await asyncio.start_server(
        client_connected, host=bind_address, port=0, family=socket.AF_INET
    )
    server_port = server.sockets[0].getsockname()[1] if server.sockets else 0
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=server_port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    monkeypatch.setattr("aiosmtplib.protocol.MAX_RESPONSE_LENGTH", 128)

    with pytest.raises(SMTPResponseException) as exc_info:
        await protocol.execute_command(b"TEST", timeout=1.0)  # type: ignore

    assert exc_info.value.code == -1
    assert "Response too long" in exc_info.value.message

    server.close()
    await cleanup_server(server)


async def test_protocol_response_continuation_overrun(
    bind_address: str,
    hostname: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_loop = asyncio.get_running_loop()

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1000)
        # Endless multiline continuation; each line is well under the per-line
        # cap, so only the total response cap can stop it.
        writer.write(b"250-spam\r\n" * 100)
        await writer.drain()

    server = await asyncio.start_server(
        client_connected, host=bind_address, port=0, family=socket.AF_INET
    )
    server_port = server.sockets[0].getsockname()[1] if server.sockets else 0
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=server_port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    monkeypatch.setattr("aiosmtplib.protocol.MAX_RESPONSE_LENGTH", 128)

    with pytest.raises(SMTPResponseException) as exc_info:
        await protocol.execute_command(b"TEST", timeout=1.0)  # type: ignore

    assert exc_info.value.code == -1
    assert "Response too long" in exc_info.value.message

    server.close()
    await cleanup_server(server)


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
    bind_address: str,
    hostname: str,
    client_tls_context: ssl.SSLContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Bytes a MITM injects after the 220 STARTTLS reply must not survive into the
    encrypted session.
    """
    event_loop = asyncio.get_running_loop()

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.readuntil(b"\r\n")
        # 220 reply plus injected plaintext, in a single segment.
        writer.write(b"220 Go ahead\r\n250-mx.evil\r\n250 AUTH LOGIN\r\n")
        await writer.drain()
        await reader.read()  # keep the connection open through start_tls

    server = await asyncio.start_server(
        client_connected, host=bind_address, port=0, family=socket.AF_INET
    )
    server_port = server.sockets[0].getsockname()[1] if server.sockets else 0
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=server_port
    )
    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    captured: dict[str, bytes] = {}

    async def mock_start_tls(transport, proto, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["buffer"] = bytes(proto._buffer)
        return transport

    monkeypatch.setattr(event_loop, "start_tls", mock_start_tls)

    response = await protocol.start_tls(client_tls_context, timeout=1.0)  # type: ignore[union-attr]

    assert response.code == 220
    assert captured["buffer"] == b""

    server.close()
    await cleanup_server(server)


async def test_error_on_readline_with_partial_line(
    bind_address: str, hostname: str
) -> None:
    event_loop = asyncio.get_running_loop()
    partial_response = b"499 incomplete response\\"

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writer.write(partial_response)
        writer.write_eof()
        await writer.drain()

    server = await asyncio.start_server(
        client_connected, host=bind_address, port=0, family=socket.AF_INET
    )
    server_port = server.sockets[0].getsockname()[1] if server.sockets else 0

    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=server_port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    with pytest.raises(SMTPServerDisconnected):
        await protocol.read_response(timeout=1.0)  # type: ignore

    server.close()
    await cleanup_server(server)


async def test_protocol_error_on_readline_with_malformed_response(
    bind_address: str, hostname: str
) -> None:
    event_loop = asyncio.get_running_loop()
    response = b"ERROR\n"

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writer.write(response)
        writer.write_eof()
        await writer.drain()

    server = await asyncio.start_server(
        client_connected, host=bind_address, port=0, family=socket.AF_INET
    )
    server_port = server.sockets[0].getsockname()[1] if server.sockets else 0

    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=server_port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    with pytest.raises(
        SMTPResponseException, match="Malformed SMTP response line: ERROR"
    ):
        await protocol.read_response(timeout=1.0)  # type: ignore

    server.close()
    await cleanup_server(server)


async def test_protocol_response_waiter_unset(
    bind_address: str,
    hostname: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_loop = asyncio.get_running_loop()

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1000)
        writer.write(b"220 Hi\r\n")
        await writer.drain()

    server = await asyncio.start_server(
        client_connected, host=bind_address, port=0, family=socket.AF_INET
    )
    server_port = server.sockets[0].getsockname()[1] if server.sockets else 0

    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=server_port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    monkeypatch.setattr(protocol, "_response_waiter", None)

    with pytest.raises(SMTPServerDisconnected):
        await protocol.execute_command(b"TEST", timeout=1.0)  # type: ignore

    server.close()
    await cleanup_server(server)


async def test_protocol_data_received_called_twice(
    bind_address: str,
    hostname: str,
) -> None:
    event_loop = asyncio.get_running_loop()

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1000)
        writer.write(b"220 Hi\r\n")
        await writer.drain()
        await asyncio.sleep(0)
        writer.write(b"221 Hi again!\r\n")
        await writer.drain()

    server = await asyncio.start_server(
        client_connected, host=bind_address, port=0, family=socket.AF_INET
    )
    server_port = server.sockets[0].getsockname()[1] if server.sockets else 0

    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=server_port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    response = await protocol.execute_command(b"TEST", timeout=1.0)  # type: ignore

    assert response.code == 220
    assert response.message == "Hi"

    server.close()
    await cleanup_server(server)


async def test_protocol_eof_response(bind_address: str, hostname: str) -> None:
    event_loop = asyncio.get_running_loop()

    async def client_connected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writer.transport.abort()  # type: ignore

    server = await asyncio.start_server(
        client_connected, host=bind_address, port=0, family=socket.AF_INET
    )
    server_port = server.sockets[0].getsockname()[1] if server.sockets else 0

    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=server_port
    )
    await asyncio.wait_for(connect_future, timeout=1.0)

    server.close()
    await cleanup_server(server)


@pytest.mark.skip_if_uvloop(reason="flaky on uvloop")
async def test_protocol_exception_cleanup_warning(
    caplog: pytest.LogCaptureFixture,
    debug_event_loop: asyncio.AbstractEventLoop,
    bind_address: str,
    hostname: str,
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

    server = await asyncio.start_server(
        client_connected, host=bind_address, port=0, family=socket.AF_INET
    )
    server_port = server.sockets[0].getsockname()[1] if server.sockets else 0

    connect_future = debug_event_loop.create_connection(
        SMTPProtocol, host=hostname, port=server_port
    )
    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    await protocol.execute_command(b"HELO", timeout=1.0)
    await protocol.execute_command(b"QUIT", timeout=1.0)

    del protocol
    # Force garbage collection
    gc.collect()

    server.close()
    await cleanup_server(server)

    assert "Future exception was never retrieved" not in caplog.text


async def test_protocol_get_close_waiter() -> None:
    event_loop = asyncio.get_running_loop()
    protocol = SMTPProtocol(event_loop)

    close_waiter = protocol._get_close_waiter(None)  # type: ignore
    assert close_waiter is not None


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


class _WriteRecordingTransport(_FakeTransport):
    def __init__(self) -> None:
        super().__init__()
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)


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

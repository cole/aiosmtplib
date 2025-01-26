"""
Protocol level tests.
"""

import asyncio
import gc
import socket
import ssl

import pytest

from aiosmtplib import SMTPResponseException, SMTPServerDisconnected
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
        await protocol.execute_command(b"TEST\n", timeout=1.0)  # type: ignore

    assert exc_info.value.code == 500
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
    class MockPipe:
        def fileno(self):
            return 7

        def close(self):
            pass

    event_loop = asyncio.get_running_loop()
    pipe = MockPipe()
    connect_future = event_loop.connect_read_pipe(SMTPProtocol, pipe)
    transport, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    assert getattr(protocol, "transport", None) is transport

    with pytest.raises(RuntimeError, match="does not support writing"):
        protocol.write(b"TEST\n")

    transport.close()


async def test_protocol_reader_connected_check_on_start_tls(
    client_tls_context: ssl.SSLContext,
) -> None:
    smtp_protocol = SMTPProtocol()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.start_tls(client_tls_context, timeout=1.0)


async def test_protocol_writer_connected_check_on_start_tls(
    client_tls_context: ssl.SSLContext,
) -> None:
    smtp_protocol = SMTPProtocol()

    with pytest.raises(SMTPServerDisconnected):
        await smtp_protocol.start_tls(client_tls_context)


async def test_already_over_tls_check_on_start_tls(
    client_tls_context: ssl.SSLContext,
) -> None:
    smtp_protocol = SMTPProtocol()
    smtp_protocol._over_ssl = True

    with pytest.raises(RuntimeError, match="Already using TLS"):
        await smtp_protocol.start_tls(client_tls_context)


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


async def test_error_on_readline_with_malformed_response(
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
        await protocol.execute_command(b"TEST\n", timeout=1.0)  # type: ignore

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

    response = await protocol.execute_command(b"TEST\n", timeout=1.0)  # type: ignore

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

    await protocol.execute_command(b"HELO\n", timeout=1.0)
    await protocol.execute_command(b"QUIT\n", timeout=1.0)

    del protocol
    # Force garbage collection
    gc.collect()

    server.close()
    await cleanup_server(server)

    assert "Future exception was never retrieved" not in caplog.text


async def test_flow_control_drain():
    event_loop = asyncio.get_running_loop()

    # Adapted from stdlib
    drained = 0

    async def drainer(stream):
        nonlocal drained
        await stream._drain_helper()
        drained += 1

    stream = FlowControlMixin(event_loop)
    stream.pause_writing()
    event_loop.call_later(0.1, stream.resume_writing)
    await asyncio.gather(*[drainer(stream) for _ in range(10)])
    assert drained == 10

"""
An ``asyncio.Protocol`` subclass for lower level IO handling.
"""

import asyncio
import collections
import re
import ssl
import weakref
from typing import Any, Callable, Optional, cast

from .errors import (
    SMTPDataError,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)
from .response import SMTPResponse
from .typing import SMTPStatus


__all__ = ("SMTPProtocol",)


MAX_LINE_LENGTH = 8192
LINE_ENDINGS_REGEX = re.compile(rb"(?:\r\n|\n|\r(?!\n))")
PERIOD_REGEX = re.compile(rb"(?m)^\.")


def format_data_message(message: bytes) -> bytes:
    message = LINE_ENDINGS_REGEX.sub(b"\r\n", message)
    message = PERIOD_REGEX.sub(b"..", message)
    if not message.endswith(b"\r\n"):
        message += b"\r\n"
    message += b".\r\n"

    return message


def read_response_from_buffer(data: bytearray) -> Optional[SMTPResponse]:
    """Parse the actual SMTP response (if any) from the data buffer"""
    code = -1
    message = bytearray()
    offset = 0
    message_complete = False

    while True:
        line_end_index = data.find(b"\n", offset)
        if line_end_index == -1:
            break

        line = bytes(data[offset : line_end_index + 1])

        if len(line) > MAX_LINE_LENGTH:
            raise SMTPResponseException(
                SMTPStatus.unrecognized_command, "Response too long"
            )

        try:
            code = int(line[:3])
        except ValueError:
            error_text = line.decode("utf-8", errors="ignore")
            raise SMTPResponseException(
                SMTPStatus.invalid_response.value,
                f"Malformed SMTP response line: {error_text}",
            ) from None

        offset += len(line)
        if len(message):
            message.extend(b"\n")
        message.extend(line[4:].strip(b" \t\r\n"))
        if line[3:4] != b"-":
            message_complete = True
            break

    if message_complete:
        response = SMTPResponse(code, bytes(message).decode("utf-8", "surrogateescape"))
        del data[:offset]
        return response

    return None


class FlowControlMixin(asyncio.Protocol):
    """
    Reusable flow control logic for StreamWriter.drain().
    This implements the protocol methods pause_writing(),
    resume_writing() and connection_lost().  If the subclass overrides
    these it must call the super methods.
    StreamWriter.drain() must wait for _drain_helper() coroutine.

    Copied from stdlib as per recommendation: https://bugs.python.org/msg343685.
    Logging and asserts removed, type annotations added.
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        if loop is None:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop

        self._paused = False
        self._drain_waiters: collections.deque[asyncio.Future[None]] = (
            collections.deque()
        )
        self._connection_lost = False

    def pause_writing(self) -> None:
        self._paused = True

    def resume_writing(self) -> None:
        self._paused = False

        for waiter in self._drain_waiters:
            if not waiter.done():
                waiter.set_result(None)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        self._connection_lost = True
        # Wake up the writer(s) if currently paused.
        if not self._paused:
            return

        for waiter in self._drain_waiters:
            if not waiter.done():
                if exc is None:
                    waiter.set_result(None)
                else:
                    waiter.set_exception(exc)

    async def _drain_helper(self) -> None:
        if self._connection_lost:
            raise ConnectionResetError("Connection lost")
        if not self._paused:
            return
        waiter = self._loop.create_future()
        self._drain_waiters.append(waiter)
        try:
            await waiter
        finally:
            self._drain_waiters.remove(waiter)

    def _get_close_waiter(
        self, stream: Optional[asyncio.StreamReader]
    ) -> "asyncio.Future[None]":
        raise NotImplementedError


class StreamReaderProtocol(FlowControlMixin, asyncio.Protocol):
    """Helper class to adapt between Protocol and StreamReader.

    (This is a helper class instead of making StreamReader itself a
    Protocol subclass, because the StreamReader has other potential
    uses, and to prevent the user of the StreamReader to accidentally
    call inappropriate methods of the protocol.)

    Copied from stdlib, with some simplifications.
    """

    def __init__(
        self,
        stream_reader: asyncio.StreamReader,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        super().__init__(loop=loop)

        self._stream_reader_wr = weakref.ref(stream_reader)
        self._transport: Optional[asyncio.Transport] = None
        self._over_ssl = False
        self._closed = self._loop.create_future()

    @property
    def _stream_reader(self):
        if self._stream_reader_wr is None:
            return None
        return self._stream_reader_wr()

    def _replace_transport(self, transport: asyncio.Transport) -> None:
        self._transport = transport
        self._over_ssl = transport.get_extra_info("sslcontext") is not None
        self._stream_reader._transport = transport  # type: ignore

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = cast(asyncio.Transport, transport)
        reader = self._stream_reader
        if reader is not None:
            reader.set_transport(transport)
        self._over_ssl = transport.get_extra_info("sslcontext") is not None

    def connection_lost(self, exc: Optional[Exception]) -> None:
        reader = self._stream_reader
        if reader is not None:
            if exc is None:
                reader.feed_eof()
            else:
                reader.set_exception(exc)
        if not self._closed.done():
            if exc is None:
                self._closed.set_result(None)
            else:
                self._closed.set_exception(exc)

        super().connection_lost(exc)

        self._stream_reader_wr = None
        self._transport = None

    def data_received(self, data: bytes) -> None:
        reader = self._stream_reader
        if reader is not None:
            reader.feed_data(data)

    def eof_received(self):
        reader = self._stream_reader
        if reader is not None:
            reader.feed_eof()
        if self._over_ssl:
            # Prevent a warning in SSLProtocol.eof_received:
            # "returning true from eof_received()
            # has no effect when using ssl"
            return False
        return True

    def _get_close_waiter(
        self, stream: Optional[asyncio.StreamReader]
    ) -> "asyncio.Future[None]":
        return self._closed

    def __del__(self):
        # Prevent reports about unhandled exceptions.
        # Better than self._closed._log_traceback = False hack
        try:
            closed = self._closed
        except AttributeError:
            pass  # failed constructor
        else:
            if closed.done() and not closed.cancelled():
                closed.exception()


class SMTPStreamWriter(asyncio.StreamWriter):
    """A StreamWriter subclass for SMTP connections.

    Adds our own `start_tls` method, which is used to upgrade the connection on older
    Python versions.
    """

    _loop: asyncio.AbstractEventLoop
    _protocol: "SMTPProtocol"

    async def start_tls(
        self,
        sslcontext: ssl.SSLContext,
        *,
        server_hostname: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Upgrade an existing stream-based connection to TLS."""
        protocol = self._protocol
        await self.drain()
        new_transport = await self._loop.start_tls(
            self._transport,  # type: ignore
            protocol,
            sslcontext,
            server_side=False,
            server_hostname=server_hostname,
            **kwargs,
        )
        self._transport = new_transport
        protocol._replace_transport(new_transport)  # type: ignore


class SMTPProtocol(StreamReaderProtocol):
    def __init__(
        self,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        reader = asyncio.StreamReader(limit=MAX_LINE_LENGTH, loop=loop)

        super().__init__(reader, loop=loop)

        self._reader = reader
        self._writer = None

        self._command_lock: Optional[asyncio.Lock] = None
        self._quit_sent: Optional[bool] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        super().connection_made(transport)
        self._writer = SMTPStreamWriter(
            cast(asyncio.Transport, transport),
            self,
            self._stream_reader,
            loop=self._loop,
        )

        self._command_lock = asyncio.Lock()
        self._quit_sent = False

    def connection_lost(self, exc: Optional[Exception]) -> None:
        smtp_exc = None
        if exc:
            smtp_exc = SMTPServerDisconnected("Connection lost")
            if exc:
                smtp_exc.__cause__ = exc

        super().connection_lost(smtp_exc)

        command_lock = self._command_lock
        self._command_lock = None
        if command_lock is not None and command_lock.locked():
            command_lock.release()

        if self._writer:
            self._writer.close()
        self._writer = None
        self._transport = None

    def eof_received(self):
        super().eof_received()

        # Close the connection
        return False

    def get_transport_info(self, key: str) -> Any:
        if self._transport is None:
            return None
        return self._transport.get_extra_info(key)

    def _replace_transport(self, transport: asyncio.Transport) -> None:
        super()._replace_transport(transport)
        self._writer._transport = transport  # type: ignore

    def close(self, callback: Optional[Callable[[asyncio.Future[None]], Any]]) -> None:
        if self._writer is not None:
            self._writer.close()

        if callback:
            self._get_close_waiter(None).add_done_callback(callback)

    async def wait_closed(self) -> None:
        if self._writer is not None:
            await self._writer.wait_closed()
        await self._get_close_waiter(None)

    def is_closing(self) -> bool:
        return self._transport is None or self._transport.is_closing()

    @property
    def is_connected(self) -> bool:
        """
        Check if our transport is still connected.
        """
        return not self.is_closing()

    async def read_response(self) -> SMTPResponse:
        """
        Get a status response from the server.

        This method must be awaited once per command sent; if multiple commands
        are written to the transport without awaiting, response data will be lost.

        Returns an :class:`.response.SMTPResponse` namedtuple consisting of:
          - server response code (e.g. 250, or such, if all goes well)
          - server response string (multiline responses are converted to a
            single, multiline string).
        """

        buffer = bytearray()

        response = None
        while response is None:
            try:
                data = await self._reader.readuntil(b"\n")
            except asyncio.IncompleteReadError as exc:
                buffer.extend(exc.partial)
            else:
                buffer.extend(data)

            response = read_response_from_buffer(buffer)

            if response:
                return response

            if self.is_closing() or self._reader.at_eof():
                raise SMTPServerDisconnected("Server disconnected")

        raise RuntimeError("No response from server")

    async def write(self, data: bytes) -> None:
        if self._writer is None:
            raise RuntimeError("Writer not initialized")

        self._writer.write(data)
        await self._writer.drain()

    async def execute_command(self, *args: bytes, quit: bool = False) -> SMTPResponse:
        """
        Sends an SMTP command along with any args to the server, and returns
        a response.
        """
        if self._writer is None or self._writer.is_closing():
            raise SMTPServerDisconnected("Connection lost")
        if self._command_lock is None:
            raise RuntimeError("Command lock not initialized")

        command = b" ".join(args) + b"\r\n"

        async with self._command_lock:
            try:
                await self.write(command)
            except ConnectionResetError as exc:
                raise SMTPServerDisconnected("Connection lost") from exc

            if quit:
                self._quit_sent = True

            response = await self.read_response()

        return response

    async def execute_data_command(self, message: bytes) -> SMTPResponse:
        """
        Sends an SMTP DATA command to the server, followed by encoded message content.

        Automatically quotes lines beginning with a period per RFC821.
        Lone \\\\r and \\\\n characters are converted to \\\\r\\\\n
        characters.
        """
        if self._writer is None or self._writer.is_closing():
            raise SMTPServerDisconnected("Connection lost")
        if self._command_lock is None:
            raise RuntimeError("Command lock not initialized")

        formatted_message = format_data_message(message)

        async with self._command_lock:
            await self.write(b"DATA\r\n")

            start_response = await self.read_response()
            if start_response.code != SMTPStatus.start_input:
                raise SMTPDataError(start_response.code, start_response.message)

            await self.write(formatted_message)

            response = await self.read_response()
            if response.code != SMTPStatus.completed:
                raise SMTPDataError(response.code, response.message)

        return response

    async def start_tls(
        self,
        tls_context: ssl.SSLContext,
        server_hostname: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> SMTPResponse:
        """
        Puts the connection to the SMTP server into TLS mode.
        """
        if self._writer is None or self._writer.is_closing():
            raise SMTPServerDisconnected("Connection lost")
        if self._over_ssl:
            raise RuntimeError("Already using TLS")
        if self._command_lock is None:
            raise RuntimeError("Command lock not initialized")

        async with self._command_lock:
            await self.write(b"STARTTLS\r\n")
            response = await self.read_response()
            if response.code != SMTPStatus.ready:
                raise SMTPResponseException(response.code, response.message)

            # Check for disconnect after response
            if self._writer.is_closing():
                raise SMTPServerDisconnected("Connection lost")

            try:
                await self._writer.start_tls(
                    tls_context,
                    server_hostname=server_hostname,
                    ssl_handshake_timeout=timeout,
                )
            except (TimeoutError, asyncio.TimeoutError) as exc:
                raise SMTPTimeoutError("Timed out while upgrading transport") from exc
            # SSLProtocol only raises ConnectionAbortedError on timeout
            except ConnectionAbortedError as exc:
                raise SMTPTimeoutError(
                    "Connection aborted while upgrading transport"
                ) from exc
            except ConnectionError as exc:
                raise SMTPServerDisconnected(
                    "Connection reset while upgrading transport"
                ) from exc

        return response

"""
An ``asyncio.Protocol`` subclass for lower level IO handling.
"""

import asyncio
import collections
import re
import ssl
from typing import Any, Optional, cast

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
        self, stream: Optional[asyncio.StreamWriter]
    ) -> "asyncio.Future[None]":
        raise NotImplementedError


class SMTPProtocol(FlowControlMixin, asyncio.BaseProtocol):
    def __init__(
        self,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        super().__init__(loop=loop)
        self._over_ssl = False
        self._buffer = bytearray()
        self._response: Optional[SMTPResponse] = None
        self._response_waiter: Optional[asyncio.Future[None]] = None
        self._exception: Optional[Exception] = None
        self._closed: "asyncio.Future[None]" = self._loop.create_future()
        self._transport: Optional[asyncio.Transport] = None

        self._command_lock: Optional[asyncio.Lock] = None
        self._quit_sent = False

    # Core state methods. These are called in order of:
    # connection_made -> data_received* -> eof_received? -> connection_lost

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = cast(asyncio.Transport, transport)
        self._over_ssl = transport.get_extra_info("sslcontext") is not None
        self._response_waiter = self._loop.create_future()
        self._command_lock = asyncio.Lock()
        self._quit_sent = False

    def connection_lost(self, exc: Optional[Exception]) -> None:
        smtp_exc = None
        if exc:
            smtp_exc = SMTPServerDisconnected("Connection lost")
            if exc:
                smtp_exc.__cause__ = exc

        if smtp_exc and not self._quit_sent:
            self._set_exception(smtp_exc)

        if self._closed and not self._closed.done():
            if smtp_exc is None:
                self._closed.set_result(None)
            else:
                self._closed.set_exception(smtp_exc)

        super().connection_lost(exc)

        self._command_lock = None
        self._transport = None

    def data_received(self, data: bytes) -> None:
        self._buffer.extend(data)

        # If we got an obvious partial message, don't try to parse the buffer
        last_linebreak = data.rfind(b"\n")
        if (
            last_linebreak == -1
            or data[last_linebreak + 3 : last_linebreak + 4] == b"-"
        ):
            return

        try:
            response = read_response_from_buffer(self._buffer)
        except Exception as exc:
            self._set_exception(exc)
        else:
            if response is not None:
                self._set_response(response)

    def eof_received(self) -> bool:
        self._set_exception(SMTPServerDisconnected("Unexpected EOF received"))

        # Returning false closes the transport
        return False

    # Transport wrappers

    def get_transport_info(self, key: str) -> Any:
        if self._transport is None:
            return None
        return self._transport.get_extra_info(key)

    def set_transport(self, transport: asyncio.Transport) -> None:
        if self._transport is not None:
            raise RuntimeError("Transport already set")
        self._transport = transport

    def _replace_transport(self, transport: asyncio.Transport) -> None:
        self._transport = transport
        self._over_ssl = transport.get_extra_info("sslcontext") is not None

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()

    def is_closing(self) -> bool:
        return bool(self._transport and self._transport.is_closing())

    # Helper methods similar to those on asyncio.StreamWriter/StreamReader

    def _get_close_waiter(
        self, stream: Optional[asyncio.StreamWriter]
    ) -> "asyncio.Future[None]":
        return self._closed

    def __del__(self) -> None:
        # Avoid 'Future exception was never retrieved' warnings
        try:
            closed = self._closed
        except AttributeError:
            pass  # failed constructor
        else:
            if closed.done() and not closed.cancelled():
                closed.exception()

    async def wait_closed(self) -> None:
        await self._get_close_waiter(None)

    def _set_exception(self, exc: Exception) -> None:
        self._exception = exc

        waiter = self._response_waiter
        if waiter is not None:
            self._response_waiter = None
            if not waiter.cancelled():
                waiter.set_exception(exc)

    def _set_response(self, response: Optional[SMTPResponse]) -> None:
        self._response = response
        self._wakeup_waiter()

    def _wakeup_waiter(self) -> None:
        waiter = self._response_waiter
        if waiter is not None:
            self._response_waiter = None
            if not waiter.cancelled():
                waiter.set_result(None)

    # SMTP specific methods

    @property
    def is_connected(self) -> bool:
        """
        Check if our transport is still connected.
        """
        return bool(self._transport is not None and not self.is_closing())

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
        if self._response_waiter is None:
            raise SMTPServerDisconnected("Connection lost")

        try:
            await self._response_waiter
        except asyncio.CancelledError as exc:
            raise SMTPTimeoutError("Timed out while waiting for response") from exc
        response = self._response
        self._response = None

        # If we were disconnected, don't create a new waiter
        if self._transport is None or self.is_closing():
            self._response_waiter = None
        else:
            self._response_waiter = self._loop.create_future()

        if response is None:
            raise RuntimeError("Invalid state: missing response")

        return response

    def write(self, data: bytes) -> None:
        if self._transport is None or self.is_closing():
            raise SMTPServerDisconnected("Connection lost")

        try:
            cast(asyncio.WriteTransport, self._transport).write(data)
        # uvloop raises NotImplementedError, asyncio doesn't have a write method
        except (AttributeError, NotImplementedError):
            raise RuntimeError(
                f"Transport {self._transport!r} does not support writing."
            ) from None

    async def execute_command(
        self, *args: bytes, timeout: Optional[float] = None, quit: bool = False
    ) -> SMTPResponse:
        """
        Sends an SMTP command along with any args to the server, and returns
        a response.
        """
        if self._command_lock is None:
            raise SMTPServerDisconnected("Server not connected")
        command = b" ".join(args) + b"\r\n"

        async with self._command_lock:
            self.write(command)

            if quit:
                self._quit_sent = True

            try:
                response = await asyncio.wait_for(self.read_response(), timeout)
            except asyncio.TimeoutError as exc:
                raise SMTPTimeoutError("Timed out while waiting for response") from exc

        return response

    async def execute_data_command(
        self, message: bytes, timeout: Optional[float] = None
    ) -> SMTPResponse:
        """
        Sends an SMTP DATA command to the server, followed by encoded message content.

        Automatically quotes lines beginning with a period per RFC821.
        Lone \\\\r and \\\\n characters are converted to \\\\r\\\\n
        characters.
        """
        if self._command_lock is None:
            raise SMTPServerDisconnected("Server not connected")

        formatted_message = format_data_message(message)

        async with self._command_lock:
            self.write(b"DATA\r\n")
            try:
                start_response = await asyncio.wait_for(self.read_response(), timeout)
            except asyncio.TimeoutError as exc:
                raise SMTPTimeoutError("Timed out while waiting for response") from exc
            if start_response.code != SMTPStatus.start_input:
                raise SMTPDataError(start_response.code, start_response.message)

            self.write(formatted_message)
            try:
                response = await asyncio.wait_for(self.read_response(), timeout)
            except asyncio.TimeoutError as exc:
                raise SMTPTimeoutError("Timed out while waiting for response") from exc
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
        if self._over_ssl:
            raise RuntimeError("Already using TLS.")
        if self._transport is None or self._command_lock is None:
            raise SMTPServerDisconnected("Server not connected")

        async with self._command_lock:
            self.write(b"STARTTLS\r\n")
            try:
                response = await asyncio.wait_for(self.read_response(), timeout)
            except asyncio.TimeoutError as exc:
                raise SMTPTimeoutError("Timed out while waiting for response") from exc
            if response.code != SMTPStatus.ready:
                raise SMTPResponseException(response.code, response.message)

            # Check for disconnect after response
            if self.is_closing():
                raise SMTPServerDisconnected("Connection lost")

            try:
                tls_transport = await self._loop.start_tls(
                    cast(asyncio.WriteTransport, self._transport),
                    self,
                    tls_context,
                    server_side=False,
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

            if tls_transport is None:
                raise SMTPServerDisconnected("Failed to upgrade transport")

            self._replace_transport(tls_transport)

        return response

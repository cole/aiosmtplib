"""
An ``asyncio.Protocol`` subclass for lower level IO handling.

Much of this code is copied from the asyncio source, since inheritance from
StreamReaderProtocol is not supported.
"""
import asyncio
import re
import ssl
from typing import Any, Optional, Union, cast

from .compat import start_tls
from .errors import (
    SMTPReadTimeoutError,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)
from .response import SMTPResponse
from .status import SMTPStatus


__all__ = ("SMTPProtocol",)


MAX_LINE_LENGTH = 8192
LINE_ENDINGS_REGEX = re.compile(rb"(?:\r\n|\n|\r(?!\n))")
PERIOD_REGEX = re.compile(rb"(?m)^\.")


class SMTPProtocol(asyncio.Protocol):
    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self._loop = loop or asyncio.get_event_loop()
        self._transport = None  # type: Optional[asyncio.Transport]
        self._over_ssl = False
        self._eof = False
        self._reading_paused = False
        self._writing_paused = False
        self._read_buffer = bytearray()
        self._write_buffer = bytearray()
        self._exception = None  # type: Optional[Exception]
        self._read_waiter = None  # type: Optional[asyncio.Future]
        self._closed = self._loop.create_future()
        self._io_lock = asyncio.Lock(loop=self._loop)

    @property
    def is_connected(self) -> bool:
        """
        Check if our transport is still connected.
        """
        return bool(self._transport is not None and not self._transport.is_closing())

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = cast(asyncio.Transport, transport)
        self._over_ssl = transport.get_extra_info("sslcontext") is not None

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc is not None:
            try:
                raise SMTPServerDisconnected("Connection lost") from exc
            except SMTPServerDisconnected as smtp_exc:
                self.set_exception(smtp_exc)

        self._transport = None

    def data_received(self, data: bytes) -> None:
        if not data:
            return

        self._read_buffer.extend(data)
        self._wakeup_waiter()

        # If we have too much data, try to pause
        if (
            self._transport is not None
            and not self._reading_paused
            and len(self._read_buffer) > 2 * MAX_LINE_LENGTH
        ):
            try:
                self._transport.pause_reading()
            except NotImplementedError:
                # The transport can't be paused.
                # We'll just have to buffer all data.
                pass
            else:
                self._reading_paused = True

    def eof_received(self) -> bool:
        self._eof = True
        self._wakeup_waiter()

        return False

    def _get_close_waiter(self, stream: Any) -> asyncio.Future:
        return self._closed

    def __del__(self):
        # Prevent reports about unhandled exceptions.
        # Better than self._closed._log_traceback = False hack
        if self._closed.done() and not self._closed.cancelled():
            self._closed.exception()

        if (
            self._read_waiter is not None
            and self._read_waiter.done()
            and not self._read_waiter.cancelled()
        ):
            self._read_waiter.exception()

    def set_exception(self, exc: Exception) -> None:
        self._exception = exc

        read_waiter = self._read_waiter
        if read_waiter is not None:
            self._read_waiter = None
            if not read_waiter.cancelled():
                read_waiter.set_exception(exc)

        if not (self._closed.done() or self._closed.cancelled()):
            self._closed.set_exception(exc)

    def _raise_if_disconnected(self):
        if self._transport is None:
            raise SMTPServerDisconnected("Client not connected")
        if self._exception:
            raise self._exception

    def _wakeup_waiter(self) -> None:
        """Wakeup read*() functions waiting for data or EOF."""
        waiter = self._read_waiter
        if waiter is not None:
            self._read_waiter = None
            if not waiter.cancelled():
                waiter.set_result(None)

    def _maybe_resume_reading(self) -> None:
        if self._transport is None:
            return

        if self._reading_paused and len(self._read_buffer) <= MAX_LINE_LENGTH:
            self._reading_paused = False
            self._transport.resume_reading()

    async def _wait_for_data(self) -> None:
        """Wait until feed_data() or feed_eof() is called.
        If stream was paused, automatically resume it.
        """
        # StreamReader uses a future to link the protocol feed_data() method
        # to a read coroutine. Running two read coroutines at the same time
        # would have an unexpected behaviour. It would not possible to know
        # which coroutine would get the next data.
        if self._read_waiter is not None:
            raise RuntimeError(
                "_wait_for_data called while another coroutine is "
                "already waiting for incoming data"
            )
        if self._transport is None:
            raise RuntimeError("_wait_for_data called with no transport set")
        if self._eof:
            raise RuntimeError("_wait_for_data after EOF")

        # Waiting for data while paused will make deadlock, so prevent it.
        # This is essential for readexactly(n) for case when n > limit.
        if self._reading_paused:
            self._reading_paused = False
            self._transport.resume_reading()

        self._read_waiter = self._loop.create_future()
        try:
            await self._read_waiter
        finally:
            self._read_waiter = None

    async def readuntil(self, separator=b"\n") -> bytes:
        """Read data from the stream until ``separator`` is found.
        On success, the data and separator will be removed from the
        internal buffer (consumed). Returned data will include the
        separator at the end.
        """
        seplen = len(separator)
        if seplen == 0:
            raise ValueError("Separator should be at least one-byte string")

        if self._exception is not None:
            raise self._exception

        # Consume whole buffer except last bytes, which length is
        # one less than seplen. Let's check corner cases with
        # separator='SEPARATOR':
        # * we have received almost complete separator (without last
        #   byte). i.e buffer='some textSEPARATO'. In this case we
        #   can safely consume len(separator) - 1 bytes.
        # * last byte of buffer is first byte of separator, i.e.
        #   buffer='abcdefghijklmnopqrS'. We may safely consume
        #   everything except that last byte, but this require to
        #   analyze bytes of buffer that match partial separator.
        #   This is slow and/or require FSM. For this case our
        #   implementation is not optimal, since require rescanning
        #   of data that is known to not belong to separator. In
        #   real world, separator will not be so long to notice
        #   performance problems. Even when reading MIME-encoded
        #   messages :)

        # `offset` is the number of bytes from the beginning of the buffer
        # where there is no occurrence of `separator`.
        offset = 0

        # Loop until we find `separator` in the buffer, exceed the buffer size,
        # or an EOF has happened.
        while True:
            buflen = len(self._read_buffer)

            # Check if we now have enough data in the buffer for `separator` to
            # fit.
            if buflen - offset >= seplen:
                isep = self._read_buffer.find(separator, offset)

                if isep != -1:
                    # `separator` is in the buffer. `isep` will be used later
                    # to retrieve the data.
                    break

                # see upper comment for explanation.
                offset = buflen + 1 - seplen
                if offset > MAX_LINE_LENGTH:
                    raise SMTPResponseException(
                        SMTPStatus.unrecognized_command, "Line too long."
                    )

            # Complete message (with full separator) may be present in buffer
            # even when EOF flag is set. This may happen when the last chunk
            # adds data which makes separator be found. That's why we check for
            # EOF *after* inspecting the buffer.
            if self._eof:
                chunk = bytes(self._read_buffer)
                self._read_buffer.clear()
                raise asyncio.IncompleteReadError(chunk, None)

            # _wait_for_data() will resume reading if stream was paused.
            await self._wait_for_data()

        if isep > MAX_LINE_LENGTH:
            raise SMTPResponseException(
                SMTPStatus.unrecognized_command, "Line too long."
            )

        chunk = self._read_buffer[: isep + seplen]
        del self._read_buffer[: isep + seplen]
        self._maybe_resume_reading()

        return bytes(chunk)

    async def read_response(
        self, timeout: Optional[Union[float, int]] = None
    ) -> SMTPResponse:
        """
        Get a status reponse from the server.

        Returns an SMTPResponse namedtuple consisting of:
          - server response code (e.g. 250, or such, if all goes well)
          - server response string corresponding to response code (multiline
            responses are converted to a single, multiline string).
        """
        self._raise_if_disconnected()

        code = None
        response_lines = []

        while True:
            read_task = self._loop.create_task(self.readuntil(separator=b"\n"))
            try:
                async with self._io_lock:
                    line = await asyncio.wait_for(read_task, timeout)
            except asyncio.TimeoutError as exc:
                raise SMTPReadTimeoutError(
                    "Timed out waiting for server response"
                ) from exc
            except asyncio.IncompleteReadError as exc:
                line = exc.partial
                raise SMTPServerDisconnected("Unexpected EOF") from exc

            try:
                code = int(line[:3])
            except ValueError:
                pass

            message = line[4:].strip(b" \t\r\n").decode("utf-8", "surrogateescape")
            response_lines.append(message)

            if line[3:4] != b"-":
                break

        full_message = "\n".join(response_lines)

        if code is None:
            raise SMTPResponseException(
                SMTPStatus.invalid_response.value,
                "Malformed SMTP response: {}".format(full_message),
            )

        return SMTPResponse(code, full_message)

    def write_message_data(self, data: bytes) -> None:
        """Encode and write email message data

        Automatically quotes lines beginning with a period per RFC821.
        Lone \\\\r and \\\\n characters are converted to \\\\r\\\\n
        characters.
        """
        data = LINE_ENDINGS_REGEX.sub(b"\r\n", data)
        data = PERIOD_REGEX.sub(b"..", data)
        if not data.endswith(b"\r\n"):
            data += b"\r\n"
        data += b".\r\n"

        self.write(data)

    def write(self, data: bytes) -> None:
        self._raise_if_disconnected()
        assert self._transport is not None  # nosec

        self._transport.write(data)

    async def execute_command(
        self, *args: bytes, timeout: Optional[Union[float, int]] = None
    ) -> SMTPResponse:
        """
        Sends an SMTP command along with any args to the server, and returns
        a response.
        """
        command = b" ".join(args) + b"\r\n"

        self.write(command)
        response = await self.read_response(timeout=timeout)

        return response

    async def start_tls(
        self,
        tls_context: ssl.SSLContext,
        server_hostname: Optional[str] = None,
        timeout: Optional[Union[float, int]] = None,
    ) -> asyncio.Transport:
        """
        Puts the connection to the SMTP server into TLS mode.
        """
        if self._over_ssl:
            raise RuntimeError("Already using TLS.")
        if self._transport is None:
            raise SMTPServerDisconnected("Client not connected")
        if self._exception:
            raise self._exception

        try:
            tls_transport = await start_tls(
                self._loop,
                self._transport,
                self,
                tls_context,
                server_side=False,
                server_hostname=server_hostname,
                ssl_handshake_timeout=timeout,
            )

        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError("Timed out while upgrading transport") from exc
        # SSLProtocol only raises ConnectionAbortedError on timeout
        except ConnectionAbortedError as exc:
            raise SMTPTimeoutError(exc.args[0]) from exc
        except ConnectionResetError as exc:
            if exc.args:
                message = exc.args[0]
            else:
                message = "Connection was reset while upgrading transport"
            raise SMTPServerDisconnected(message) from exc

        self._transport = tls_transport

        return tls_transport

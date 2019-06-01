"""
An ``asyncio.Protocol`` subclass for lower level IO handling.
"""
import asyncio
import re
import ssl
from typing import Any, Optional, Union

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


class FlowControlMixin(object):
    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        if loop is None:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop
        self._paused = False
        self._drain_waiter = None  # type: Optional[asyncio.Future]
        self._connection_lost = False

    def pause_writing(self):
        self._paused = True

    def resume_writing(self):
        self._paused = False

        waiter = self._drain_waiter
        if waiter is not None:
            self._drain_waiter = None
            if not waiter.done():
                waiter.set_result(None)

    def connection_lost(self, exc: Optional[Exception]):
        self._connection_lost = True
        # Wake up the writer if currently paused.
        if not self._paused:
            return
        waiter = self._drain_waiter
        if waiter is None:
            return
        self._drain_waiter = None
        if waiter.done():
            return
        if exc is None:
            waiter.set_result(None)
        else:
            waiter.set_exception(exc)

    async def _drain_helper(self):
        if self._connection_lost:
            raise ConnectionResetError("Connection lost")
        if not self._paused:
            return
        waiter = self._loop.create_future()
        self._drain_waiter = waiter
        await waiter


class StreamReaderProtocol(FlowControlMixin, asyncio.Protocol):
    """
    This protocol is based on asyncio.StreamReaderProtocol, but the code has
    been copied to avoid references to private attributes.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        super().__init__(loop=loop)

        self._transport = None  # type: Optional[asyncio.BaseTransport]
        self._stream_reader = reader  # type: Optional[asyncio.StreamReader]
        self._stream_writer = None  # type: Optional[asyncio.StreamWriter]
        self._over_ssl = False
        self._closed = self._loop.create_future()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        if self._stream_reader is None:
            raise RuntimeError("Connection made on protocol with no stream reader")
        # We set the _transport directly on the StreamReader, rather than calling
        # set_transport (which will raise an AssertionError on upgrade).
        # This is because on 3.5.2, we can't avoid calling connection_made on
        # upgrade.
        self._transport = transport
        self._stream_reader._transport = transport  # type: ignore
        self._over_ssl = transport.get_extra_info("sslcontext") is not None
        self._stream_writer = asyncio.StreamWriter(
            transport, self, self._stream_reader, self._loop
        )

    def connection_lost(self, exc: Optional[Exception]):
        if self._stream_reader is not None:
            if exc is None:
                self._stream_reader.feed_eof()
            else:
                self._stream_reader.set_exception(exc)
        if not self._closed.done():
            if exc is None:
                self._closed.set_result(None)
            else:
                self._closed.set_exception(exc)
        super().connection_lost(exc)

        self._stream_reader = None
        self._stream_writer = None

    def data_received(self, data: bytes):
        if self._stream_reader is None:
            raise RuntimeError("Data received on protocol with no stream reader")

        self._stream_reader.feed_data(data)

    def eof_received(self):
        if self._stream_reader is None:
            raise RuntimeError("EOF received on protocol with no stream reader")

        self._stream_reader.feed_eof()
        if self._over_ssl:
            # Prevent a warning in SSLProtocol.eof_received:
            # "returning true from eof_received()
            # has no effect when using ssl"
            return False
        return True

    def _get_close_waiter(self, stream: Any):
        return self._closed

    def __del__(self):
        # Prevent reports about unhandled exceptions.
        # Better than self._closed._log_traceback = False hack
        closed = self._closed
        if closed.done() and not closed.cancelled():
            closed.exception()


class SMTPProtocol(StreamReaderProtocol):
    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        reader = asyncio.StreamReader(limit=MAX_LINE_LENGTH, loop=loop)
        super().__init__(reader, loop=loop)

        self._io_lock = asyncio.Lock(loop=self._loop)

    async def readline_with_timeout(self, timeout: Union[float, int, None] = None):
        if self._stream_reader is None or self._transport is None:
            raise SMTPServerDisconnected("Client not connected")

        read_task = self._loop.create_task(
            self._stream_reader.readuntil(separator=b"\n")
        )
        try:
            async with self._io_lock:
                line = await asyncio.wait_for(read_task, timeout)  # type: bytes
        except asyncio.LimitOverrunError:
            raise SMTPResponseException(
                SMTPStatus.unrecognized_command, "Line too long."
            )
        except asyncio.TimeoutError:
            raise SMTPReadTimeoutError("Timed out waiting for server response")
        except asyncio.IncompleteReadError as exc:
            if exc.partial == b"":
                # if we got only an EOF, raise SMTPServerDisconnected
                raise SMTPServerDisconnected("Unexpected EOF received")
            else:
                # otherwise, close our connection but try to parse the
                # response anyways
                self._transport.close()
                line = exc.partial

        return line

    async def read_response(
        self, timeout: Union[float, int, None] = None
    ) -> SMTPResponse:
        """
        Get a status reponse from the server.

        Returns an SMTPResponse namedtuple consisting of:
          - server response code (e.g. 250, or such, if all goes well)
          - server response string corresponding to response code (multiline
            responses are converted to a single, multiline string).
        """
        code = None
        response_lines = []

        while True:
            line = await self.readline_with_timeout(timeout=timeout)
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

    async def write_message_data(
        self, data: bytes, timeout: Union[float, int, None] = None
    ) -> None:
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

        await self.write_and_drain(data, timeout=timeout)

    async def write_and_drain(
        self, data: bytes, timeout: Union[float, int, None] = None
    ) -> None:
        if self._stream_writer is None:
            raise SMTPServerDisconnected("Client not connected")

        self._stream_writer.write(data)
        try:
            async with self._io_lock:
                await asyncio.wait_for(self._stream_writer.drain(), timeout)
        except ConnectionError as exc:
            raise SMTPServerDisconnected(str(exc))
        except asyncio.TimeoutError:
            raise SMTPTimeoutError("Timed out on write")

    async def execute_command(
        self, *args: bytes, timeout: Union[float, int, None] = None
    ) -> SMTPResponse:
        """
        Sends an SMTP command along with any args to the server, and returns
        a response.
        """
        command = b" ".join(args) + b"\r\n"

        await self.write_and_drain(command, timeout=timeout)
        response = await self.read_response(timeout=timeout)

        return response

    async def start_tls(
        self,
        tls_context: ssl.SSLContext,
        server_hostname: Optional[str] = None,
        timeout: Union[float, int, None] = None,
    ) -> asyncio.Transport:
        """
        Puts the connection to the SMTP server into TLS mode.
        """
        if self._over_ssl:
            raise RuntimeError("Already using TLS.")

        if (
            self._transport is None
            or self._stream_reader is None
            or self._stream_writer is None
        ):
            raise SMTPServerDisconnected("Client not connected")

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

        except asyncio.TimeoutError:
            raise SMTPTimeoutError("Timed out while upgrading transport")
        # SSLProtocol only raises ConnectionAbortedError on timeout
        except ConnectionAbortedError as exc:
            raise SMTPTimeoutError(exc.args[0])
        except ConnectionResetError as exc:
            if exc.args:
                message = exc.args[0]
            else:
                message = "Connection was reset while upgrading transport"
            raise SMTPServerDisconnected(message)

        self._transport = tls_transport
        self._stream_reader._transport = tls_transport  # type: ignore
        self._stream_writer._transport = tls_transport  # type: ignore

        return tls_transport

    # Backwards compatibility shim
    starttls = start_tls

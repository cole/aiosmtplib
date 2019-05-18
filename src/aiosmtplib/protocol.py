"""
An ``asyncio.Protocol`` subclass for lower level IO handling.
"""
import asyncio
import re
import ssl
from asyncio.sslproto import SSLProtocol  # type: ignore
from typing import Awaitable, Optional, Tuple, Union  # NOQA

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


StartTLSResponse = Tuple[SMTPResponse, SSLProtocol]
NumType = Union[float, int]


class FlowControlMixin(object):
    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        if loop is None:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop
        self._paused = False
        self._drain_waiter = None
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

    def connection_lost(self, exc):
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


class SMTPStreamReader(asyncio.StreamReader):

    _loop = None  # type: asyncio.AbstractEventLoop
    _transport = None  # type: asyncio.BaseTransport

    async def readline_with_timeout(self, timeout: NumType = None):
        read_task = asyncio.Task(self.readuntil(separator=b"\n"), loop=self._loop)
        try:
            line = await asyncio.wait_for(
                read_task, timeout, loop=self._loop
            )  # type: bytes
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

    async def read_response(self, timeout: NumType = None) -> SMTPResponse:
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


class SMTPStreamWriter(asyncio.StreamWriter):

    _loop = None  # type: asyncio.AbstractEventLoop
    _transport = None  # type: asyncio.BaseTransport

    async def drain_with_timeout(self, timeout: NumType = None) -> None:
        # Wrapping drain in a task makes mypy happy
        drain_task = asyncio.Task(super().drain(), loop=self._loop)
        try:
            await asyncio.wait_for(drain_task, timeout, loop=self._loop)
        except ConnectionError as exc:
            raise SMTPServerDisconnected(str(exc))
        except asyncio.TimeoutError:
            raise SMTPTimeoutError("Timed out on write")

    async def write_command(self, *args: bytes, timeout: NumType = None) -> None:
        """Send a formatted SMTP command along with any args to the server
        """
        command = b" ".join(args) + b"\r\n"

        self.write(command)
        await self.drain_with_timeout(timeout=timeout)

    async def write_message_data(self, data: bytes, timeout: NumType = None) -> None:
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
        await self.drain_with_timeout(timeout=timeout)


class SMTPStreamReaderProtocol(FlowControlMixin, asyncio.Protocol):
    """
    This protocol is based on asyncio.StreamReaderProtocol, but the code has
    been copied to avoid references to private attributes.
    """

    def __init__(
        self, reader: SMTPStreamReader, loop: asyncio.AbstractEventLoop = None
    ) -> None:
        super().__init__(loop=loop)

        self._stream_reader = reader
        self._stream_writer = None  # type: Optional[SMTPStreamWriter]
        self._over_ssl = False
        self._closed = self._loop.create_future()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        # We set the _transport directly on the StreamReader, rather than calling
        # set_transport (which will raise an AssertionError on upgrade).
        # This is because on 3.5.2, we can't avoid calling connection_made on
        # upgrade.
        self._stream_reader._transport = transport
        self._over_ssl = transport.get_extra_info("sslcontext") is not None
        self._stream_writer = SMTPStreamWriter(
            transport, self, self._stream_reader, self._loop
        )

    def connection_lost(self, exc):
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

    def data_received(self, data):
        self._stream_reader.feed_data(data)

    def eof_received(self):
        self._stream_reader.feed_eof()
        if self._over_ssl:
            # Prevent a warning in SSLProtocol.eof_received:
            # "returning true from eof_received()
            # has no effect when using ssl"
            return False
        return True

    def _get_close_waiter(self, stream):
        return self._closed

    def __del__(self):
        # Prevent reports about unhandled exceptions.
        # Better than self._closed._log_traceback = False hack
        closed = self._closed
        if closed.done() and not closed.cancelled():
            closed.exception()


class SMTPProtocol(SMTPStreamReaderProtocol):
    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        reader = SMTPStreamReader(limit=MAX_LINE_LENGTH, loop=loop)
        super().__init__(reader, loop=loop)

        self._io_lock = asyncio.Lock(loop=self._loop)

    async def read_response(self, timeout: NumType = None) -> SMTPResponse:
        if self._stream_reader is None:
            raise SMTPServerDisconnected("Client not connected")

        async with self._io_lock:
            response = await self._stream_reader.read_response(timeout=timeout)

        return response

    async def write_message_data(self, data, timeout: NumType = None) -> None:
        if self._stream_writer is None:
            raise SMTPServerDisconnected("Client not connected")

        async with self._io_lock:
            await self._stream_writer.write_message_data(data, timeout=timeout)

    async def write_and_drain(self, data, timeout: NumType = None) -> None:
        if self._stream_writer is None:
            raise SMTPServerDisconnected("Client not connected")

        self._stream_writer.write(data)
        async with self._io_lock:
            await self._stream_writer.drain_with_timeout(timeout=timeout)

    def upgrade_transport(
        self,
        context: ssl.SSLContext,
        server_hostname: str = None,
        waiter: Awaitable = None,
    ) -> SSLProtocol:
        """
        Upgrade our transport to TLS in place.
        """
        if self._over_ssl:
            raise RuntimeError("Already using TLS.")

        if self._stream_reader is None or self._stream_writer is None:
            raise SMTPServerDisconnected("Client not connected")

        transport = self._stream_reader._transport

        tls_protocol = SSLProtocol(
            self._loop,
            self,
            context,
            waiter,
            server_side=False,
            server_hostname=server_hostname,
        )

        app_transport = tls_protocol._app_transport
        # Use set_protocol if we can
        if hasattr(transport, "set_protocol"):
            transport.set_protocol(tls_protocol)  # type: ignore
        else:
            transport._protocol = tls_protocol  # type: ignore

        self._stream_reader._transport = app_transport
        self._stream_writer._transport = app_transport

        tls_protocol.connection_made(transport)
        self._over_ssl = True  # type: bool

        return tls_protocol

    async def execute_command(
        self, *args: bytes, timeout: NumType = None
    ) -> SMTPResponse:
        """
        Sends an SMTP command along with any args to the server, and returns
        a response.
        """
        if self._stream_reader is None or self._stream_writer is None:
            raise SMTPServerDisconnected("Client not connected")

        async with self._io_lock:
            await self._stream_writer.write_command(*args, timeout=timeout)
            response = await self._stream_reader.read_response(timeout=timeout)

        return response

    async def starttls(
        self,
        tls_context: ssl.SSLContext,
        server_hostname: str = None,
        timeout: NumType = None,
    ) -> StartTLSResponse:
        """
        Puts the connection to the SMTP server into TLS mode.
        """
        response = await self.execute_command(b"STARTTLS", timeout=timeout)

        if response.code != SMTPStatus.ready:
            raise SMTPResponseException(response.code, response.message)

        if self._stream_writer is None:
            raise SMTPServerDisconnected("Client not connected")

        await self._stream_writer.drain_with_timeout(timeout=timeout)

        waiter = asyncio.Future(loop=self._loop)  # type: asyncio.Future
        tls_protocol = self.upgrade_transport(
            tls_context, server_hostname=server_hostname, waiter=waiter
        )

        try:
            await asyncio.wait_for(waiter, timeout=timeout, loop=self._loop)
        except asyncio.TimeoutError:
            raise SMTPTimeoutError("Timed out while upgrading transport")

        return response, tls_protocol

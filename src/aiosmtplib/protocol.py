"""
An ``asyncio.Protocol`` subclass for lower level IO handling.
"""
import asyncio
import re
import ssl
from typing import Callable, Optional, cast

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
    def __init__(
        self,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        connection_lost_callback: Optional[Callable] = None,
    ) -> None:
        self._loop = loop or asyncio.get_event_loop()
        self._over_ssl = False
        self._buffer = bytearray()
        self._response_waiter = None  # type: Optional[asyncio.Future[SMTPResponse]]
        self._connection_lost_callback = connection_lost_callback
        self._connection_lost_waiter = None  # type: Optional[asyncio.Future[None]]

        self.transport = None  # type: Optional[asyncio.Transport]

    def __del__(self):
        waiters = (self._response_waiter, self._connection_lost_waiter)
        for waiter in filter(None, waiters):
            if waiter.done() and not waiter.cancelled():
                # Avoid 'Future exception was never retrieved' warnings
                waiter.exception()

    @property
    def is_connected(self) -> bool:
        """
        Check if our transport is still connected.
        """
        return bool(self.transport is not None and not self.transport.is_closing())

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = cast(asyncio.Transport, transport)
        self._over_ssl = transport.get_extra_info("sslcontext") is not None
        self._response_waiter = self._loop.create_future()

        if self._connection_lost_callback is not None:
            self._connection_lost_waiter = self._loop.create_future()
            self._connection_lost_waiter.add_done_callback(
                self._connection_lost_callback
            )

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc:
            smtp_exc = SMTPServerDisconnected("Server disconnected unexpectedly")
            smtp_exc.__cause__ = exc

        if self._response_waiter and not self._response_waiter.done():
            if exc:
                self._response_waiter.set_exception(smtp_exc)
            else:
                self._response_waiter.cancel()

        if self._connection_lost_waiter and not self._connection_lost_waiter.done():
            if exc:
                self._connection_lost_waiter.set_exception(smtp_exc)
            else:
                self._connection_lost_waiter.set_result(None)

        self.transport = None

    def data_received(self, data: bytes) -> None:
        if data == b"":
            return

        if self._response_waiter is None or self._response_waiter.done():
            raise RuntimeError(
                "data_received called with an unexpected response waiter state: "
                "{!r} (data: {})".format(self._response_waiter, data)
            )

        self._buffer.extend(data)

        # If we got an obvious partial message, don't try to parse the buffer
        last_linebreak = data.rfind(b"\n")
        if (
            last_linebreak == -1
            or data[last_linebreak + 3 : last_linebreak + 4] == b"-"
        ):
            return

        try:
            response = self._read_response_from_buffer()
        except Exception as exc:
            self._response_waiter.set_exception(exc)
        else:
            if response is not None:
                self._response_waiter.set_result(response)

    def eof_received(self) -> bool:
        exc = SMTPServerDisconnected("Unexpected EOF received")
        if self._response_waiter and not self._response_waiter.done():
            self._response_waiter.set_exception(exc)
        if self._connection_lost_waiter and not self._connection_lost_waiter.done():
            self._connection_lost_waiter.set_exception(exc)

        # Returning false closes the transport
        return False

    def _read_response_from_buffer(self) -> Optional[SMTPResponse]:
        """Parse the actual response (if any) from the data buffer
        """
        code = -1
        message = bytearray()
        offset = 0
        message_complete = False

        while True:
            line_end_index = self._buffer.find(b"\n", offset)
            if line_end_index == -1:
                break

            line = bytes(self._buffer[offset : line_end_index + 1])

            if len(line) > MAX_LINE_LENGTH:
                raise SMTPResponseException(
                    SMTPStatus.unrecognized_command, "Response too long"
                )

            try:
                code = int(line[:3])
            except ValueError:
                raise SMTPResponseException(
                    SMTPStatus.invalid_response.value,
                    "Malformed SMTP response line: {}".format(line),
                ) from None

            offset += len(line)
            if len(message):
                message.extend(b"\n")
            message.extend(line[4:].strip(b" \t\r\n"))
            if line[3:4] != b"-":
                message_complete = True
                break

        if message_complete:
            response = SMTPResponse(
                code, bytes(message).decode("utf-8", "surrogateescape")
            )
            del self._buffer[:offset]
            return response
        else:
            return None

    async def read_response(self, timeout: Optional[float] = None) -> SMTPResponse:
        """
        Get a status reponse from the server.

        This method must be awaited once per command sent; if multiple commands
        are written to the transport without awaiting, response data will be lost.

        Returns an :class:`.response.SMTPResponse` namedtuple consisting of:
          - server response code (e.g. 250, or such, if all goes well)
          - server response string (multiline responses are converted to a
            single, multiline string).
        """
        if self._response_waiter is None:
            raise SMTPServerDisconnected("Client not connected")

        try:
            result = await asyncio.wait_for(self._response_waiter, timeout)
        except asyncio.TimeoutError as exc:
            raise SMTPReadTimeoutError("Timed out waiting for server response") from exc
        finally:
            # If we were disconnected, don't create a new waiter
            if self.transport is None:
                self._response_waiter = None
            else:
                self._response_waiter = self._loop.create_future()

        return result

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
        if self.transport is None or self.transport.is_closing():
            raise SMTPServerDisconnected("Client not connected")

        self.transport.write(data)

    async def execute_command(
        self, *args: bytes, timeout: Optional[float] = None
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
        timeout: Optional[float] = None,
    ) -> asyncio.Transport:
        """
        Puts the connection to the SMTP server into TLS mode.
        """
        if self._over_ssl:
            raise RuntimeError("Already using TLS.")
        if self.transport is None or self.transport.is_closing():
            raise SMTPServerDisconnected("Not connected")

        try:
            tls_transport = await start_tls(
                self._loop,
                self.transport,
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

        self.transport = tls_transport

        return tls_transport

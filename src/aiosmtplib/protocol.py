"""
aiosmtplib.protocol
===================

An ``asyncio.Protocol`` subclass for lower level IO handling.
"""
import asyncio
import re
import ssl
from asyncio.sslproto import SSLProtocol  # type: ignore
from typing import Awaitable, Optional, Tuple, Union  # NOQA

from .errors import (
    SMTPResponseException, SMTPServerDisconnected, SMTPTimeoutError,
)
from .response import SMTPResponse
from .status import SMTPStatus


__all__ = ('SMTPProtocol',)


LINE_ENDINGS_REGEX = re.compile(b'(?:\r\n|\n|\r(?!\n))')
PERIOD_REGEX = re.compile(b'(?m)^\.')


StartTLSResponse = Tuple[SMTPResponse, SSLProtocol]
NumType = Union[float, int]


class SMTPProtocol(asyncio.StreamReaderProtocol):
    """
    SMTPProtocol handles sending and recieving data, through interactions
    with ``asyncio.StreamReader`` and ``asyncio.StreamWriter``.

    We use a locking primitive when reading/writing to ensure that we don't
    have multiple coroutines waiting for reads/writes at the same time.
    """

    def __init__(
            self, reader: asyncio.StreamReader,
            loop: asyncio.AbstractEventLoop = None) -> None:
        self._stream_reader = None  # type: Optional[asyncio.StreamReader]
        self._stream_writer = None  # type: Optional[asyncio.StreamWriter]
        self._loop = loop or asyncio.get_event_loop()

        super().__init__(  # type: ignore
            reader, client_connected_cb=self.on_connect, loop=self._loop)

        self._io_lock = asyncio.Lock(loop=self._loop)

    def on_connect(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._stream_reader = reader
        self._stream_writer = writer

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """
        Modified ``connection_made`` that supports upgrading our transport in
        place using STARTTLS.

        The only difference here from StreamReaderProtocol's version is we
        are setting the _transport directly on the StreamReader, rather than
        calling set_transport (which will raise an AssertionError on upgrade).
        """
        self._stream_reader._transport = transport  # type: ignore
        self._over_ssl = transport.get_extra_info('sslcontext') is not None
        if self._client_connected_cb is not None:  # type: ignore
            self._stream_writer = asyncio.StreamWriter(
                transport, self, self._stream_reader,
                self._loop)  # type: ignore
            res = self._client_connected_cb(  # type: ignore
                self._stream_reader, self._stream_writer)
            if asyncio.iscoroutine(res):
                self._loop.create_task(res)  # type: ignore

    def upgrade_transport(
            self, context: ssl.SSLContext, server_hostname: str = None,
            waiter: Awaitable = None) -> SSLProtocol:
        """
        Upgrade our transport to TLS in place.
        """
        assert self._stream_reader is not None, 'Client not connected'
        assert self._stream_writer is not None, 'Client not connected'
        assert not self._over_ssl, 'Already using TLS'

        transport = self._stream_reader._transport  # type: ignore

        tls_protocol = SSLProtocol(
            self._loop, self, context, waiter, server_side=False,
            server_hostname=server_hostname)

        app_transport = tls_protocol._app_transport  # type: ignore
        # Use set_protocol if we can
        if hasattr(transport, 'set_protocol'):
            transport.set_protocol(tls_protocol)
        else:
            transport._protocol = tls_protocol  # type: ignore

        self._stream_reader._transport = app_transport  # type: ignore
        self._stream_writer._transport = app_transport  # type: ignore

        tls_protocol.connection_made(transport)
        self._over_ssl = True  # type: bool

        return tls_protocol

    async def read_response(self, timeout: NumType = None) -> SMTPResponse:
        """
        Get a status reponse from the server.

        Returns an SMTPResponse namedtuple consisting of:
          - server response code (e.g. 250, or such, if all goes well)
          - server response string corresponding to response code (multiline
            responses are converted to a single, multiline string).
        """
        assert self._stream_reader is not None, 'Client not connected'

        code = None
        response_lines = []

        while True:
            async with self._io_lock:
                line = await self._readline(timeout=timeout)
            try:
                code = int(line[:3])
            except ValueError:
                pass

            message = line[4:].strip(b' \t\r\n').decode('ascii')
            response_lines.append(message)

            if line[3:4] != b'-':
                break

        full_message = '\n'.join(response_lines)

        if code is None:
            raise SMTPResponseException(
                SMTPStatus.invalid_response.value,
                'Malformed SMTP response: {}'.format(full_message))

        return SMTPResponse(code, full_message)

    async def write_and_drain(
            self, data: bytes, timeout: NumType = None) -> None:
        """
        Format a command and send it to the server.
        """
        assert self._stream_writer is not None, 'Client not connected'

        self._stream_writer.write(data)

        async with self._io_lock:
            await self._drain_writer(timeout)

    async def write_message_data(
            self, data: bytes, timeout: NumType = None) -> None:
        """
        Encode and write email message data.

        Automatically quotes lines beginning with a period per RFC821.
        Lone '\r' and '\n' characters are converted to '\r\n' characters.
        """
        data = LINE_ENDINGS_REGEX.sub(b'\r\n', data)
        data = PERIOD_REGEX.sub(b'..', data)
        if not data.endswith(b'\r\n'):
            data += b'\r\n'
        data += b'.\r\n'

        await self.write_and_drain(data, timeout=timeout)

    async def execute_command(
            self, *args: bytes, timeout: NumType = None) -> SMTPResponse:
        """
        Sends an SMTP command along with any args to the server, and returns
        a response.
        """
        command = b' '.join(args) + b'\r\n'

        await self.write_and_drain(command, timeout=timeout)
        response = await self.read_response(timeout=timeout)

        return response

    async def starttls(
            self, tls_context: ssl.SSLContext, server_hostname: str = None,
            timeout: NumType = None) -> StartTLSResponse:
        """
        Puts the connection to the SMTP server into TLS mode.
        """
        assert self._stream_writer is not None, 'Client not connected'

        response = await self.execute_command(b'STARTTLS', timeout=timeout)

        if response.code != SMTPStatus.ready:
            raise SMTPResponseException(response.code, response.message)

        await self._drain_writer(timeout)

        waiter = asyncio.Future(loop=self._loop)  # type: asyncio.Future

        tls_protocol = self.upgrade_transport(
            tls_context, server_hostname=server_hostname, waiter=waiter)

        await asyncio.wait_for(waiter, timeout=timeout, loop=self._loop)

        return response, tls_protocol

    async def _drain_writer(self, timeout: NumType = None) -> None:
        """
        Wraps writer.drain() with error handling.
        """
        assert self._stream_writer is not None, 'Client not connected'

        # Wrapping drain in a task makes mypy happy
        drain_task = asyncio.Task(self._stream_writer.drain(), loop=self._loop)
        try:
            await asyncio.wait_for(drain_task, timeout, loop=self._loop)
        except ConnectionError as exc:
            raise SMTPServerDisconnected(str(exc))
        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError(str(exc))

    async def _readline(self, timeout: NumType = None):
        """
        Wraps reader.readuntil() with error handling.
        """
        read_task = asyncio.Task(
            self._stream_reader.readuntil(separator=b'\n'), loop=self._loop)
        try:
            line = await asyncio.wait_for(
                read_task, timeout, loop=self._loop)  # type: bytes
        except ConnectionError as exc:
            raise SMTPServerDisconnected(str(exc))
        except asyncio.LimitOverrunError:
            raise SMTPResponseException(500, 'Line too long.')
        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError(str(exc))
        except asyncio.IncompleteReadError as exc:
            if exc.partial == b'':  # type: ignore
                # if we got only an EOF, raise SMTPServerDisconnected
                raise SMTPServerDisconnected('Unexpected EOF received')
            else:
                # otherwise, close our connection but try to parse the
                # response anyways
                self._stream_writer.close()
                line = exc.partial  # type: ignore

        return line

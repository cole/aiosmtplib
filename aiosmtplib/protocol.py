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

from aiosmtplib.errors import (
    SMTPResponseException, SMTPServerDisconnected, SMTPTimeoutError,
)
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus


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
        self.reader = None  # type: Optional[asyncio.StreamReader]
        self.writer = None  # type: Optional[asyncio.StreamWriter]
        self.loop = loop or asyncio.get_event_loop()

        def _client_connected(
                reader: asyncio.StreamReader,
                writer: asyncio.StreamWriter) -> None:
            self.reader = reader
            self.writer = writer

        super().__init__(  # type: ignore
            reader, client_connected_cb=_client_connected, loop=self.loop)

        self._io_lock = asyncio.Lock(loop=self.loop)

    def upgrade_transport(
            self, context: ssl.SSLContext, server_hostname: str = None,
            waiter: Awaitable = None) -> SSLProtocol:
        """
        Upgrade our transport to TLS in place.
        """
        assert self.reader is not None, 'Client not connected'
        assert self.writer is not None, 'Client not connected'
        assert not self._over_ssl, 'Already using TLS'

        plain_transport = self.reader._transport  # type: ignore

        tls_protocol = SSLProtocol(
            self.loop, self, context, waiter, server_side=False,
            server_hostname=server_hostname, call_connection_made=False)

        # This assignment seems a bit strange, but is all required.
        self.reader._transport._protocol = tls_protocol  # type: ignore
        self.reader._transport = tls_protocol._app_transport  # type: ignore
        self.writer._transport._protocol = tls_protocol  # type: ignore
        self.writer._transport = tls_protocol._app_transport  # type: ignore

        tls_protocol.connection_made(plain_transport)
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
        assert self.reader is not None, 'Client not connected'

        code = None
        response_lines = []

        while True:
            async with self._io_lock:
                read_coro = self.reader.readline()
                try:
                    line = await asyncio.wait_for(
                        read_coro, timeout, loop=self.loop)  # type: bytes
                except asyncio.LimitOverrunError:
                    raise SMTPResponseException(500, 'Line too long.')
                except ConnectionError as exc:
                    raise SMTPServerDisconnected(str(exc))
                except asyncio.TimeoutError as exc:
                    raise SMTPTimeoutError(str(exc))

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
        assert self.writer is not None, 'Client not connected'

        self.writer.write(data)

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
        assert self.writer is not None, 'Client not connected'

        response = await self.execute_command(b'STARTTLS', timeout=timeout)

        if response.code == SMTPStatus.ready:
            await self._drain_writer(timeout)

            waiter = asyncio.Future(loop=self.loop)  # type: asyncio.Future

            tls_protocol = self.upgrade_transport(
                tls_context, server_hostname=server_hostname, waiter=waiter)

            await asyncio.wait_for(waiter, timeout=timeout, loop=self.loop)

        return response, tls_protocol

    async def _drain_writer(self, timeout: NumType = None) -> None:
        assert self.writer is not None, 'Client not connected'

        # Wrapping drain in a task makes mypy happy
        # drain_task = asyncio.Task(, loop=self.loop)
        try:
            await asyncio.wait_for(self.writer.drain(), timeout, loop=self.loop)
        except ConnectionError as exc:
            raise SMTPServerDisconnected(str(exc))
        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError(str(exc))

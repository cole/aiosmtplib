"""
aiosmtplib.protocol
===================

SMTPProtocol class, for lower level IO handling
"""
import asyncio
import re
import ssl
from asyncio.sslproto import SSLProtocol  # type: ignore
from typing import Awaitable, Tuple

from aiosmtplib.errors import (
    SMTPResponseException, SMTPServerDisconnected, SMTPTimeoutError,
)
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus
from aiosmtplib.typing import OptionalNumber

__all__ = ('SMTPProtocol',)


LINE_ENDINGS_REGEX = re.compile(b'(?:\r\n|\n|\r(?!\n))')
PERIOD_REGEX = re.compile(b'(?m)^\.')


class SMTPProtocol(asyncio.StreamReaderProtocol):

    def __init__(
            self, reader: asyncio.StreamReader,
            loop: asyncio.AbstractEventLoop = None) -> None:
        if loop is None:
            loop = asyncio.get_event_loop()

        self._stream_reader = None  # type: asyncio.StreamReader
        self._stream_writer = None  # type: asyncio.StreamWriter
        super().__init__(
            reader, client_connected_cb=None, loop=loop)

        self.loop = loop
        self.reader = self._stream_reader

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        # TODO: We won't need this anymore where 3.5.3 is released (hopefully)
        self._stream_reader._transport = transport  # type: ignore
        self._over_ssl = transport.get_extra_info('sslcontext') is not None

        if self._stream_writer is None:
            self._stream_writer = asyncio.StreamWriter(
                transport, self, self._stream_reader, self.loop)

        self.writer = self._stream_writer
        self.transport = transport

    def upgrade_transport(
            self, context: ssl.SSLContext, server_hostname: str = None,
            waiter: Awaitable = None) -> SSLProtocol:
        """
        Upgrade our transport to TLS in place.
        """
        assert not self._over_ssl, 'Already using TLS'

        plain_transport = self.transport

        tls_protocol = SSLProtocol(
            self.loop, self, context, waiter, server_side=False,
            server_hostname=server_hostname)

        # This assignment is required, even though it's done again in
        # connection_made
        app_transport = tls_protocol._app_transport  # type: ignore
        self.reader._transport._protocol = tls_protocol  # type: ignore
        self.reader._transport = app_transport  # type: ignore
        self.writer._transport._protocol = tls_protocol  # type: ignore
        self.writer._transport = app_transport  # type: ignore

        tls_protocol.connection_made(plain_transport)
        self._over_ssl = True

        return tls_protocol

    async def read_response(
            self, timeout: OptionalNumber = None) -> SMTPResponse:
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
            self, data: bytes, timeout: OptionalNumber = None) -> None:
        """
        Format a command and send it to the server.
        """
        self.writer.write(data)

        drain_coro = self.writer.drain()  # type: ignore
        try:
            asyncio.wait_for(drain_coro, timeout, loop=self.loop)
        except ConnectionError as exc:
            raise SMTPServerDisconnected(str(exc))
        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError(str(exc))

    async def write_message_data(
            self, data: bytes, timeout: OptionalNumber = None) -> None:
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
            self, *args: str,
            timeout: OptionalNumber = None) -> SMTPResponse:
        command = b' '.join([arg.encode('ascii') for arg in args]) + b'\r\n'

        await self.write_and_drain(command, timeout=timeout)
        response = await self.read_response(timeout=timeout)

        if response.code == SMTPStatus.domain_unavailable:
            self.transport.close()
            raise SMTPResponseException(response.code, response.message)

        return response

    async def starttls(
            self, tls_context: ssl.SSLContext,
            server_hostname: str = None,
            timeout: OptionalNumber = None) -> \
            Tuple[SMTPResponse, SSLProtocol]:
        """
        Puts the connection to the SMTP server into TLS mode.
        """
        response = await self.execute_command('STARTTLS', timeout=timeout)

        if response.code == SMTPStatus.ready:
            drain_coro = self._stream_writer.drain()  # type: ignore
            try:
                await asyncio.wait_for(
                    drain_coro, timeout=timeout, loop=self.loop)
            except ConnectionError as exc:
                raise SMTPServerDisconnected(str(exc))
            except asyncio.TimeoutError as exc:
                raise SMTPTimeoutError(str(exc))

            waiter = asyncio.Future(loop=self.loop)  # type: asyncio.Future

            tls_protocol = self.upgrade_transport(
                tls_context, server_hostname=server_hostname, waiter=waiter)

            await asyncio.wait_for(waiter, timeout=timeout, loop=self.loop)

        return response, tls_protocol

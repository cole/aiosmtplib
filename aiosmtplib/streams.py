import asyncio
from asyncio.sslproto import SSLProtocol, _SSLProtocolTransport  # type: ignore
from ssl import SSLContext
from typing import Awaitable, Tuple, Union

from aiosmtplib.errors import (
    SMTPConnectError, SMTPResponseException, SMTPServerDisconnected,
    SMTPTimeoutError,
)
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus

MAX_LINE_LENGTH = 8192


class SMTPProtocol(asyncio.StreamReaderProtocol):

    def __init__(
            self, reader: asyncio.StreamReader,
            loop: asyncio.AbstractEventLoop = None) -> None:
        if loop is None:
            loop = asyncio.get_event_loop()

        self.loop = loop

        super().__init__(  # type: ignore
            reader, client_connected_cb=self.client_connected,
            loop=self.loop)

    def client_connected(
            self, reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """
        TODO: We won't need this anymore where 3.5.3 is released (hopefully)
        """
        self.transport = transport
        if isinstance(transport, _SSLProtocolTransport):
            # STARTTLS connection over normal connection
            self._stream_reader._transport = transport  # type: ignore
            self._over_ssl = True
        else:
            super().connection_made(transport)

    def connection_lost(self, exc):
        super().connection_lost(exc)
        self.reader = None
        self.writer = None
        self.transport = None

    def start_tls(
            self, context: SSLContext, server_hostname: str = None,
            waiter: Awaitable = None) -> SSLProtocol:
        """
        Upgrade our transport to TLS in place.
        """
        assert not self._over_ssl, 'Already using TLS'

        plain_transport = self._stream_reader._transport  # type: ignore
        loop = self._loop  # type: ignore

        tls_protocol = SSLProtocol(
            loop, self, context, waiter, server_side=False,
            server_hostname=server_hostname)

        # This assignment is required, even though it's done again in
        # connection_made
        app_transport = tls_protocol._app_transport  # type: ignore
        self._stream_reader._transport._protocol = tls_protocol  # type: ignore
        self._stream_reader._transport = app_transport  # type: ignore

        tls_protocol.connection_made(plain_transport)
        self._over_ssl = True

        return tls_protocol


class SMTPStreamReader(asyncio.StreamReader):

    def __init__(self, limit=MAX_LINE_LENGTH, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

        super().__init__(limit=limit, loop=loop)

    async def read_response(self) -> SMTPResponse:
        """
        Get a status reponse from the server.

        Returns a tuple consisting of:

          - server response code (e.g. 250, or such, if all goes well)

          - server response string corresponding to response code (multiline
            responses are converted to a single, multiline string).

        Raises SMTPResponseException for codes > 500.
        """
        code = None
        response_lines = []

        while True:
            try:
                line = await self.readline()  # type: bytes
            except asyncio.LimitOverrunError:
                raise SMTPResponseException(500, 'Line too long.')
            except ConnectionError as exc:
                raise SMTPServerDisconnected(str(exc))

            try:
                code = int(line[:3])
            except ValueError:
                pass

            message = line[4:].strip(b' \t\r\n').decode('ascii')
            response_lines.append(message)

            if line[3:4] != b'-':
                break

        full_message = '\n'.join(response_lines)

        if code is None and self.at_eof():
            raise SMTPServerDisconnected('Server disconnected unexpectedly')
        elif code is None:
            raise SMTPResponseException(
                SMTPStatus.invalid_response.value,
                'Malformed SMTP response: {}'.format(full_message))

        return SMTPResponse(code, full_message)


class SMTPStreamWriter(asyncio.StreamWriter):

    def __init__(self, transport, protocol, reader, loop):
        self.loop = loop
        self.reader = reader
        self.protocol = protocol
        super().__init__(transport, protocol, reader, loop)

    async def send_command(self, command: bytes) -> None:
        """
        Format a command and send it to the server.
        """
        self.write(command + b'\r\n')

        try:
            await self.drain()  # type: ignore
        except ConnectionError as exc:
            raise SMTPServerDisconnected(str(exc))

    async def execute_command(
            self, *args: str,
            timeout: Union[int, float, None] = None) -> SMTPResponse:
        """
        Send the commands given and return the reply message.
        """
        assert self.reader is not None

        command = b' '.join([arg.encode('ascii') for arg in args])

        write_coroutine = self.send_command(command)
        read_coroutine = self.reader.read_response()
        waiter = asyncio.gather(
            write_coroutine, read_coroutine, loop=self.loop)

        try:
            results = await asyncio.wait_for(waiter, timeout, loop=self.loop)
        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError(str(exc))

        return results[1]

    async def queue_command(
            self, *args: str,
            timeout: Union[int, float, None] = None) -> \
            Awaitable[SMTPResponse]:
        """
        Send the commands given and return a future, the result of which
        will be the reply message.
        Whereas execute command waits for the response, queue_command does not
        for pipelining support.
        """
        assert self.reader is not None

        command = b' '.join([arg.encode('ascii') for arg in args])

        write_coroutine = self.send_command(command)
        read_coroutine = self.reader.read_response()

        try:
            await asyncio.wait_for(write_coroutine, timeout, loop=self.loop)
        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError(str(exc))

        return asyncio.ensure_future(read_coroutine, loop=self.loop)

    async def start_tls(
            self, context: SSLContext, server_hostname: str = None,
            timeout: Union[int, float, None] = None) -> \
            Tuple[SSLProtocol, asyncio.BaseTransport]:
        drain_future = self.drain()  # type: ignore
        try:
            await asyncio.wait_for(
                drain_future, timeout=timeout, loop=self.loop)
        except ConnectionError as exc:
            raise SMTPServerDisconnected(str(exc))
        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError(str(exc))

        waiter = asyncio.Future(loop=self.loop)  # type: asyncio.Future

        tls_protocol = self.protocol.start_tls(
            context, server_hostname=server_hostname, waiter=waiter)

        self._transport = tls_protocol._app_transport  # type: ignore

        await asyncio.wait_for(waiter, timeout=timeout, loop=self.loop)

        return tls_protocol, tls_protocol._app_transport


async def open_connection(hostname, port, loop, timeout, tls_context):
    """
    Version of asyncio's open connection, but we use SMTP classes,
    and also return the transport and protocol.
    """
    reader = SMTPStreamReader(loop=loop)
    protocol = SMTPProtocol(reader, loop=loop)

    connect_future = loop.create_connection(
        lambda: protocol, host=hostname, port=port,
        ssl=tls_context)  # type: ignore
    try:
        transport, _ = await asyncio.wait_for(  # type: ignore
            connect_future, timeout=timeout, loop=loop)
    except (ConnectionRefusedError, OSError) as err:
        raise SMTPConnectError(
            'Error connecting to {host} on port {port}: {err}'.format(
                host=hostname, port=port, err=err))
    except asyncio.TimeoutError as exc:
        raise SMTPTimeoutError(str(exc))

    writer = SMTPStreamWriter(transport, protocol, reader, loop)

    return reader, writer, transport, protocol

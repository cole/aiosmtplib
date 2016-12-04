import asyncio
from asyncio.sslproto import SSLProtocol, _SSLProtocolTransport  # type: ignore
from ssl import SSLContext
from typing import Awaitable, Tuple, Union

from aiosmtplib import status
from aiosmtplib.errors import (
    SMTPResponseException, SMTPServerDisconnected, SMTPTimeoutError,
)


class SMTPProtocol(asyncio.StreamReaderProtocol):

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """
        TODO: We won't need this anymore where 3.5.3 is released (hopefully)
        """
        if isinstance(transport, _SSLProtocolTransport):
            # STARTTLS connection over normal connection
            self._stream_reader._transport = transport  # type: ignore
            self._over_ssl = True
        else:
            super().connection_made(transport)

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

    async def read_response(
            self, timeout: Union[int, float, None] = None) -> Tuple[int, str]:
        """
        Get a status reponse from the server.

        Returns a tuple consisting of:

          - server response code (e.g. 250, or such, if all goes well)

          - server response string corresponding to response code (multiline
            responses are converted to a single, multiline string).

        Raises SMTPResponseException for codes > 500.
        """
        loop = self._loop  # type: ignore
        code = status.SMTP_NO_RESPONSE_CODE
        response_lines = []

        while True:
            line_future = self.readline()  # type: Awaitable
            try:
                line = await asyncio.wait_for(
                    line_future, timeout=timeout, loop=loop)  # type: bytes
            except asyncio.TimeoutError as exc:
                raise SMTPTimeoutError(str(exc))
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

        if code == status.SMTP_NO_RESPONSE_CODE and self.at_eof():
            raise SMTPServerDisconnected('Server disconnected unexpectedly')

        return code, full_message


class SMTPStreamWriter(asyncio.StreamWriter):

    async def send_command(
            self, command: bytes,
            timeout: Union[int, float, None] = None) -> None:
        """
        Format a command and send it to the server.
        """
        self.write(command + b'\r\n')

        drain_future = self.drain()  # type: ignore
        loop = self._loop  # type: ignore
        try:
            await asyncio.wait_for(drain_future, timeout=timeout, loop=loop)
        except ConnectionError as exc:
            raise SMTPServerDisconnected(str(exc))
        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError(str(exc))

    async def start_tls(
            self, context: SSLContext, server_hostname: str = None,
            timeout: Union[int, float, None] = None) -> \
            Tuple[SSLProtocol, asyncio.BaseTransport]:
        drain_future = self.drain()  # type: ignore
        loop = self._loop  # type: ignore
        try:
            await asyncio.wait_for(
                drain_future, timeout=timeout, loop=loop)
        except ConnectionError as exc:
            raise SMTPServerDisconnected(str(exc))
        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError(str(exc))

        loop = self._loop  # type: ignore
        protocol = self._protocol  # type: ignore
        waiter = asyncio.Future(loop=loop)  # type: asyncio.Future

        tls_protocol = protocol.start_tls(
            context, server_hostname=server_hostname, waiter=waiter)

        self._transport = tls_protocol._app_transport  # type: ignore

        await asyncio.wait_for(waiter, timeout=timeout, loop=loop)

        return tls_protocol, tls_protocol._app_transport

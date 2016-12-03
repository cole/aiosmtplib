import asyncio
from asyncio.sslproto import SSLProtocol, _SSLProtocolTransport  # type: ignore
from ssl import SSLContext
from typing import Awaitable, Tuple

from aiosmtplib import status
from aiosmtplib.errors import SMTPServerDisconnected


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

    async def read_response(self) -> Tuple[int, str]:
        """
        Get a status reponse from the server.

        Returns a tuple consisting of:

          - server response code (e.g. 250, or such, if all goes well)

          - server response string corresponding to response code (multiline
            responses are converted to a single, multiline string).

        Raises SMTPResponseException for codes > 500.
        """
        code = status.SMTP_NO_RESPONSE_CODE
        response_lines = []

        while True:
            try:
                line = await self.readline()
            # TODO: alternative to LimitOverrunError
            # except LimitOverrunError:
            #     raise SMTPResponseException(500, 'Line too long.'')
            except ConnectionResetError as exc:
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

    async def send_command(self, command: bytes) -> None:
        """
        Format a command and send it to the server.
        """
        self.write(command + b'\r\n')

        try:
            await self.drain()  # type: ignore
        except ConnectionResetError as exc:
            raise SMTPServerDisconnected(str(exc))

    async def start_tls(
            self, context: SSLContext, server_hostname: str = None) -> \
            Tuple[SSLProtocol, asyncio.BaseTransport]:
        try:
            await self.drain()  # type: ignore
        except ConnectionResetError as exc:
            raise SMTPServerDisconnected(str(exc))

        loop = self._loop  # type: ignore
        protocol = self._protocol  # type: ignore
        waiter = asyncio.Future(loop=loop)  # type: asyncio.Future

        tls_protocol = protocol.start_tls(
            context, server_hostname=server_hostname, waiter=waiter)

        self._transport = tls_protocol._app_transport  # type: ignore

        await waiter

        return tls_protocol, tls_protocol._app_transport

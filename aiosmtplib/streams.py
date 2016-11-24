import asyncio
import asyncio.selector_events
import asyncio.sslproto

from aiosmtplib.errors import SMTPServerDisconnected


class SMTPProtocol(asyncio.StreamReaderProtocol):

    def connection_made(self, transport):
        '''
        TODO: We won't need this anymore where 3.5.3 is released (hopefully)
        '''
        if isinstance(transport, asyncio.sslproto._SSLProtocolTransport):
            # STARTTLS connection over normal connection
            self._stream_reader._transport = transport
            self._over_ssl = True
        else:
            super().connection_made(transport)

    def start_tls(self, ssl_context, server_hostname=None, waiter=None):
        '''
        Upgrade our transport to TLS in place.
        '''
        assert not self._over_ssl, 'Already using TLS'

        plain_transport = self._stream_reader._transport

        tls_protocol = asyncio.sslproto.SSLProtocol(
            self._loop, self, ssl_context, waiter, server_side=False,
            server_hostname=server_hostname)

        # This assignment is required, even though it's done again in
        # connection_made
        self._stream_reader._transport._protocol = tls_protocol
        self._stream_reader._transport = tls_protocol._app_transport

        tls_protocol.connection_made(plain_transport)
        self._over_ssl = True

        return tls_protocol


class SMTPStreamReader(asyncio.StreamReader):

    async def read_response(self):
        '''
        Get a status reponse from the server.

        Returns a tuple consisting of:

          - server response code (e.g. 250, or such, if all goes well)

          - server response string corresponding to response code (multiline
            responses are converted to a single, multiline string).

        Raises SMTPResponseException for codes > 500.
        '''
        code = None
        response_lines = []

        while True:
            try:
                line = await self.readline()
            # TODO: alternative to LimitOverrunError
            # except LimitOverrunError:
            #     raise SMTPResponseException(500, 'Line too long.'')
            except ConnectionResetError as exc:
                raise SMTPServerDisconnected(exc)

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

        return code, full_message


class SMTPStreamWriter(asyncio.StreamWriter):

    async def send_command(self, *args):
        '''
        Format a command and send it to the server.
        '''
        command = '{}\r\n'.format(' '.join(args)).encode('ascii')
        self.write(command)

        await self.drain()

    async def start_tls(self, ssl_context, server_hostname=None):
        await self.drain()

        waiter = asyncio.Future(loop=self._loop)

        tls_protocol = self._protocol.start_tls(
            ssl_context, server_hostname=server_hostname, waiter=waiter)

        self._transport = tls_protocol._app_transport

        await waiter

        return tls_protocol, tls_protocol._app_transport

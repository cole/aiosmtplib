import asyncio
import collections
import logging
import socket
import ssl

from .sslproto import SSLProtocol


logger = logging.getLogger(__name__)


class PresetServer:
    """
    Basic request/response server, with TLS & upgrade connection support.
    """

    def __init__(self, hostname, port, loop=None,
                 certfile='tests/certs/selfsigned.crt',
                 keyfile='tests/certs/selfsigned.key', use_tls=False):
        super().__init__()
        self.hostname = hostname
        self.port = port
        self.loop = loop
        self.certfile = certfile
        self.keyfile = keyfile
        self.use_tls = use_tls

        self.responses = collections.deque()
        self.requests = []
        self.delay_next_response = 0

        self.closed = False
        self.server, self.stream_reader, self.stream_writer = None, None, None

        self.drop_connection_event = asyncio.Event(loop=self.loop)
        self.drop_connection_after_request = None
        self.drop_connection_after_response = None

    @property
    def request_delimiter(self):
        return b'\n'

    def next_response(self):
        response = self.responses.popleft()

        if (self.drop_connection_after_response and
                response == self.drop_connection_after_response):
            self.drop_connection_event.set()

        return bytes(response)

    def _bind_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((self.hostname, self.port))
        except OSError:
            logger.exception(
                'Error occurred binding to %s on port %s', self.hostname,
                self.port)
            raise

        if self.port == 0:
            self.port = socket.getsockname()[1]

        return sock

    async def start(self):
        sock = self._bind_socket()
        tls_context = self.tls_context if self.use_tls else None

        self.server = await asyncio.start_server(
            self.handle_connection, ssl=tls_context, sock=sock, loop=self.loop)

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()

    async def handle_connection(self, reader, writer):
        self.stream_reader = reader
        self.stream_writer = writer

        await self.send_greeting()

        await self.process_requests()

        if not self.drop_connection_event.is_set():
            await self.send_goodbye()
            if self.stream_writer.can_write_eof():
                self.stream_writer.write_eof()
            await self.stream_writer.drain()

        self.stream_writer.close()

    async def process_requests(self):
        while not self.drop_connection_event.is_set():
            try:
                data = await asyncio.wait_for(self.read(), 1.0, loop=self.loop)
            except asyncio.TimeoutError:
                logger.debug('Read loop timed out.')
                break

            logger.debug('Data received: %s', data)

            if not data:
                break

            await self.on_request(data)

            if self.drop_connection_event.is_set():
                logger.debug('Dropping connection before response.')
                break

            try:
                response = self.next_response()
            except IndexError:
                break

            await self.write(response)
            await self.on_response(data, response)

    async def write(self, data):
        self.stream_writer.write(data)
        await self.stream_writer.drain()

    async def read(self, delimiter=None):
        """
        Read char by char so that we can drop the connection partway through a
        request. Timeout reads after 1 second.
        """
        if delimiter is None:
            delimiter = self.request_delimiter
        logger.debug('In read loop (delimiter: %s)', delimiter)

        data = bytearray()

        while not data[-len(delimiter):] == delimiter:
            chunk = await self.stream_reader.read(n=1)
            if chunk == b'':
                break

            data.extend(chunk)
            if (data == self.drop_connection_after_request):
                self.drop_connection_event.set()
                break

        return bytes(data)

    @property
    def tls_context(self):
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(self.certfile, keyfile=self.keyfile)

        return context

    def wrap_transport(self, waiter):
        old_transport = self.stream_writer._transport
        old_protocol = self.stream_writer._protocol

        tls_protocol = SSLProtocol(
            self.loop, old_protocol, self.tls_context, waiter,
            server_side=True, call_connection_made=False)
        if hasattr(old_transport, 'set_protocol'):
            old_transport.set_protocol(tls_protocol)
        else:
            old_transport._protocol = tls_protocol

        self.stream_reader._transport = tls_protocol._app_transport
        self.stream_writer._transport = tls_protocol._app_transport

        tls_protocol.connection_made(old_transport)
        tls_protocol._over_ssl = True

    async def on_request(self, data):
        self.requests.append(data)

        if self.delay_next_response > 0:
            logger.debug(
                'Delayed response %s seconds.', self.delay_next_response)
            await asyncio.sleep(self.delay_next_response, loop=self.loop)

    async def on_response(self, request, response):
        logger.debug('Response sent: %s', response)

    async def send_greeting(self):
        return

    async def send_goodbye(self):
        return


class SMTPPresetServer(PresetServer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.delay_greeting = 0
        self.greeting = b'220 Hello world!\n'
        self.goodbye = b'221 Goodbye then\n'
        self.reading_message_data = False

    @property
    def request_delimiter(self):
        return b'.\r\n' if self.reading_message_data else b'\r\n'

    def next_response(self):
        response = super().next_response()
        if not response.endswith(b'\n'):
            response = response + b'\n'

        return response

    async def on_request(self, data):
        await super().on_request(data)

        next_response_is_start_input = (
            self.responses and self.responses[0][:3] == b'354'
        )
        if data.strip() == b'DATA' and next_response_is_start_input:
            self.reading_message_data = True
        else:
            self.reading_message_data = False

    async def on_response(self, data, response):
        await super().on_response(data, response)

        if data.strip() == b'STARTTLS':
            waiter = asyncio.Future(loop=self.loop)
            self.wrap_transport(waiter)
            await asyncio.wait_for(waiter, 1.0)
            logger.debug('Transport upgraded.')

    async def send_greeting(self):
        if self.delay_greeting > 0:
            await asyncio.sleep(self.delay_greeting, loop=self.loop)
            logger.debug('Delayed greeting %s seconds.', self.delay_greeting)
        self.stream_writer.write(self.greeting)
        await self.stream_writer.drain()
        logger.debug('Greeting sent: %s', self.greeting)

    async def send_goodbye(self):
        if not self.drop_connection_event.is_set():
            self.stream_writer.write(self.goodbye)
            logger.debug('Goodbye sent: %s', self.goodbye)

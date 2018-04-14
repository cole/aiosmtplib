import asyncio
import collections
import socket
import ssl

from .sslproto import SSLProtocol


class PresetServer:

    def __init__(self, hostname, port, loop=None,
                 certfile='tests/certs/selfsigned.crt',
                 keyfile='tests/certs/selfsigned.key', use_tls=False,
                 greeting=b'220 Hello world!\n',
                 goodbye=b'221 Goodbye then\n'):

        super().__init__()
        self.hostname = hostname
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile
        self.use_tls = use_tls
        self.greeting = greeting
        self.goodbye = goodbye
        self.responses = collections.deque()
        self.requests = []
        self.delay_next_response = 0
        self.delay_greeting = 0

        self.loop = loop
        self.closed = False
        self.server, self.stream_reader, self.stream_writer = None, None, None

        self.drop_connection_event = asyncio.Event(loop=self.loop)
        self.drop_connection_after_request = None
        self.drop_connection_after_response = None

    @property
    def tls_context(self):
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(self.certfile, keyfile=self.keyfile)

        return context

    def next_response(self):
        response = self.responses.popleft()

        if (self.drop_connection_after_response and
                response == self.drop_connection_after_response):
            self.drop_connection_event.set()

        response = bytes(response)
        if response and not response.endswith(b'\n'):
            response = response + b'\n'

        return response

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

    async def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((self.hostname, self.port))

        if self.port == 0:
            self.port = socket.getsockname()[1]

        tls_context = self.tls_context if self.use_tls else None
        self.server = await asyncio.start_server(
            self.on_connect, ssl=tls_context, sock=sock, loop=self.loop)

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()

    async def on_connect(self, reader, writer):
        self.stream_reader = reader
        self.stream_writer = writer

        if self.delay_greeting > 0:
            await asyncio.sleep(self.delay_greeting, loop=self.loop)

        self.stream_writer.write(self.greeting)
        await self.stream_writer.drain()

        await self.process_requests()

        if not self.drop_connection_event.is_set():
            self.stream_writer.write(self.goodbye)
            if self.stream_writer.can_write_eof():
                self.stream_writer.write_eof()
            await self.stream_writer.drain()

        self.stream_writer.close()

    async def process_requests(self):
        reading_message_data = False

        while not self.drop_connection_event.is_set():
            if reading_message_data:
                data = await self.read(delimiter=b'.\r\n')
                reading_message_data = False
            else:
                data = await self.read(delimiter=b'\r\n')

            if not data:
                break

            self.requests.append(data)

            if self.drop_connection_event.is_set():
                break

            if self.delay_next_response > 0:
                await asyncio.sleep(self.delay_next_response, loop=self.loop)

            try:
                response = self.next_response()
            except IndexError:
                break

            await self.write(response)

            if self.drop_connection_event.is_set():
                break

            if data[:4] == b'DATA' and response[:3] == b'354':
                reading_message_data = True
            elif data[:8] == b'STARTTLS':
                waiter = asyncio.Future(loop=self.loop)
                self.wrap_transport(waiter)
                await asyncio.wait_for(waiter, 1.0)

    async def write(self, data):
        self.stream_writer.write(data)
        await self.stream_writer.drain()

    async def read(self, delimiter=b'\r\n'):
        """
        Read char by char so that we can drop the connection partway through a
        request.
        """
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

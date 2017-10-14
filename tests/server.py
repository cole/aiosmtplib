import asyncio
import asyncore
import collections
import smtpd
import socket
import ssl
import threading
from asyncio.sslproto import SSLProtocol
from email.errors import HeaderParseError


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

    @property
    def tls_context(self):
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(self.certfile, keyfile=self.keyfile)

        return context

    def next_response(self):
        response = self.responses.popleft()
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

        old_transport.set_protocol(tls_protocol)
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
        while not self.drop_connection_event.is_set():
            data = await self.stream_reader.readuntil(b'\r\n')
            self.requests.append(data)

            if self.delay_next_response > 0:
                await asyncio.sleep(self.delay_next_response, loop=self.loop)

            if self.drop_connection_event.is_set():
                break

            try:
                response = self.next_response()
            except IndexError:
                break

            self.stream_writer.write(response)
            await self.stream_writer.drain()

            if self.drop_connection_event.is_set():
                break

            if data[:8] == b'STARTTLS':
                waiter = asyncio.Future(loop=self.loop)
                self.wrap_transport(waiter)
                await asyncio.wait_for(waiter, 10.0)


class TestSMTPDChannel(smtpd.SMTPChannel):

    def _getaddr(self, arg):
        """
        Don't raise an exception on unparsable email address
        """
        try:
            return super()._getaddr(arg)
        except HeaderParseError:
            return None, ''


class TestSMTPD(smtpd.SMTPServer):
    channel_class = TestSMTPDChannel

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.messages = []

    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        self.messages.append((peer, mailfrom, rcpttos, data, kwargs))


class ThreadedSMTPDServer:

    def __init__(self, hostname, port):
        self.hostname = hostname
        self.port = port
        self.smtpd = TestSMTPD((self.hostname, self.port), None)

    def start(self):
        self.server_thread = threading.Thread(target=self.serve_forever)
        # Exit the server thread when the main thread terminates
        self.server_thread.daemon = True
        self.server_thread.start()

    def serve_forever(self):
        # We use poll here - select doesn't seem to work.
        asyncore.loop(1, True)

    def stop(self):
        self.smtpd.close()
        self.server_thread.join(timeout=0.5)

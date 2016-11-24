import asyncio
import threading
import socketserver
import selectors
import ssl
from email.errors import HeaderParseError

from aiosmtpd.smtp import SMTP as BaseSMTPD
from aiosmtpd.handlers import Sink as SMTPDSinkHandler
from aiosmtpd.controller import Controller


class ThreadedPresetRequestHandler(socketserver.BaseRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selector = selectors.DefaultSelector()

    @property
    def next_response(self):
        return self.server._next_response

    @next_response.setter
    def next_response(self, response):
        self.server.next_response = response

    def starttls(self):
        context = self.server.get_ssl_context()
        self.request.settimeout(30)
        self.request = context.wrap_socket(self.request, server_side=True)
        self.request.settimeout(None)

    def handle(self):
        self.request.sendall(b'220 Hello world!\n')
        # self.selector.register(self.request, selectors.EVENT_READ)

        while True:
            request = self.request.recv(4096)  # Naive recv won't work for data
            response = self.next_response
            if response:
                self.request.sendall(response)
            else:
                break

            if request[:8] == b'STARTTLS':
                self.starttls()

            self.next_response = b''

        # Disconnect
        self.request.sendall(b'221 Goodbye then\n')


class ThreadedPresetServer(
        socketserver.ThreadingMixIn, socketserver.TCPServer):

    def __init__(self, hostname, port, certfile='tests/certs/selfsigned.crt',
                 keyfile='tests/certs/selfsigned.key'):
        super().__init__((hostname, port), ThreadedPresetRequestHandler)
        self.hostname = hostname
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile

        self.next_response = b''

    @property
    def next_response(self):
        return self._next_response

    @next_response.setter
    def next_response(self, response):
        response = bytes(response)
        if response and not response.endswith(b'\n'):
            response = response + b'\n'

        self._next_response = response

    def start(self):
        self.server_thread = threading.Thread(target=self.serve_forever)
        # Exit the server thread when the main thread terminates
        self.server_thread.daemon = True
        self.server_thread.start()

    def stop(self):
        self.shutdown()
        self.server_close()

    def get_ssl_context(self):
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(self.certfile, keyfile=self.keyfile)

        return context


class SSLThreadedPresetServer(ThreadedPresetServer):

    def get_request(self):
        socket, from_address = self.socket.accept()
        context = self.get_ssl_context()
        ssl_socket = context.wrap_socket(socket, server_side=True)

        return ssl_socket, from_address


class AsyncioPresetServer:
    '''
    Returns only predefined responses, in order.
    '''

    def __init__(self, hostname, port, loop=None):
        self.server = None
        self.hostname = hostname
        self.port = port
        self.loop = loop or asyncio.get_event_loop()
        self.tasks = {}

        self.next_response = b'220 Hello world!'

    @property
    def next_response(self):
        return self._next_response

    @next_response.setter
    def next_response(self, response):
        response = bytes(response)
        if response and not response.endswith(b'\n'):
            response = response + b'\n'

        self._next_response = response

    async def handle_request(self, reader, writer):
        '''
        Write first, as that's what the client expects
        '''
        while True:
            response = self.next_response
            if not response:
                break

            self.next_response = b''

            writer.write(response)
            await writer.drain()
            await reader.readline()

        # Disconnect
        writer.write(b'221 Goodbye then\n')
        await writer.drain()
        writer.close()

    def on_connect(self, reader, writer):
        task = self.loop.create_task(self.handle_request(reader, writer))

        # asyncio.wait_for(task, timeout=1)
        def remove_task(task):
            del self.tasks[task]

        task.add_done_callback(remove_task)
        self.tasks[task] = reader, writer

    async def start(self):
        self.server = await asyncio.start_server(
            self.on_connect, self.hostname, self.port, loop=self.loop)

    async def stop(self):
        for task, streams in self.tasks.items():
            reader, writer = streams
            writer.close()
            task.cancel()

        self.server.close()
        await self.server.wait_closed()
        self.server = None


class SSLAsyncioPresetServer(AsyncioPresetServer):
    '''
    SSL enabled version of PresetServer.
    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        self.ssl_context.load_cert_chain(
            'tests/certs/selfsigned.crt', 'tests/certs/selfsigned.key')

    async def start(self):
        self.server = await asyncio.start_server(
            self.on_connect, self.hostname, self.port, loop=self.loop,
            ssl=self.ssl_context)


class TestSMTPD(BaseSMTPD):

    def _getaddr(self, arg):
        try:
            return super()._getaddr(arg)
        except HeaderParseError:
            return None, ''


class MessageHandler(SMTPDSinkHandler):

    def __init__(self):
        self.messages = []
        super().__init__()

    def handle_message(self, message):
        self.messages.append(message)


class AioSMTPDTestServer(Controller):

    def __init__(self):
        handler = MessageHandler()
        super().__init__(handler)

    def factory(self):
        return TestSMTPD(self.handler)

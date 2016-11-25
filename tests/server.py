import asyncio
import threading
import socketserver
import socket
import ssl
import collections
from email.errors import HeaderParseError

from aiosmtpd.smtp import SMTP as BaseSMTPD
from aiosmtpd.handlers import Sink as SMTPDSinkHandler
from aiosmtpd.controller import Controller


class ThreadedPresetRequestHandler(socketserver.BaseRequestHandler):

    def starttls(self):
        context = self.server.get_tls_context()
        self.request.settimeout(30)
        self.request = context.wrap_socket(self.request, server_side=True)
        self.request.settimeout(None)

    def handle(self):
        if self.server.send_greeting:
            self.request.sendall(b'220 Hello world!\n')

        while True:
            data = self.request.recv(4096)  # Naive recv won't work for data
            self.server.requests.append(data)

            response = self.server.next_response
            if response:
                self.request.sendall(response)
            else:
                break

            if data[:8] == b'STARTTLS':
                self.starttls()

        # Disconnect
        if self.server.send_goodbye:
            self.request.sendall(b'221 Goodbye then\n')
            try:
                self.request.shutdown(socket.SHUT_RDWR)
            except TypeError:
                self.request.shutdown()
            except OSError:
                pass
            self.request.close()


class ThreadedPresetServer(
        socketserver.ThreadingMixIn, socketserver.TCPServer):

    def __init__(self, hostname, port, certfile='tests/certs/selfsigned.crt',
                 keyfile='tests/certs/selfsigned.key', send_greeting=True,
                 send_goodbye=True):
        super().__init__((hostname, port), ThreadedPresetRequestHandler)
        self.hostname = hostname
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile

        self.send_greeting = send_greeting
        self.send_goodbye = send_goodbye
        self.responses = collections.deque()
        self.requests = []

    @property
    def next_response(self):
        try:
            response = self.responses.popleft()
        except IndexError:
            response = b''
        else:
            response = bytes(response)
            if response and not response.endswith(b'\n'):
                response = response + b'\n'

        return response

    def start(self):
        self.server_thread = threading.Thread(target=self.serve_forever)
        # Exit the server thread when the main thread terminates
        self.server_thread.daemon = True
        self.server_thread.start()

    def stop(self):
        self.shutdown()
        self.server_close()

    def get_tls_context(self):
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(self.certfile, keyfile=self.keyfile)

        return context


class TLSThreadedPresetServer(ThreadedPresetServer):

    def get_request(self):
        socket, from_address = self.socket.accept()
        context = self.get_tls_context()
        wrapped_socket = context.wrap_socket(socket, server_side=True)

        return wrapped_socket, from_address


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


class TLSAsyncioPresetServer(AsyncioPresetServer):
    '''
    TLS enabled version of PresetServer.
    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tls_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        self.tls_context.load_cert_chain(
            'tests/certs/selfsigned.crt', 'tests/certs/selfsigned.key')

    async def start(self):
        self.server = await asyncio.start_server(
            self.on_connect, self.hostname, self.port, loop=self.loop,
            ssl=self.tls_context)


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

import asyncore
import collections
import select
import smtpd
import socket
import socketserver
import ssl
import threading
import time
from email.errors import HeaderParseError


class PresetServer(threading.Thread):

    def __init__(self, hostname, port, certfile='tests/certs/selfsigned.crt',
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

        self.ready = threading.Barrier(2, timeout=2.0)
        self.stop_event = threading.Event()
        self.drop_connection_event = threading.Event()

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

    def wrap_socket(self):
        self.connection.settimeout(1)
        self.connection = self.tls_context.wrap_socket(
            self.connection, server_side=True)
        self.connection.settimeout(None)

    def handle_connection(self):
        if self.delay_greeting > 0:
            time.sleep(self.delay_greeting)

        self.connection.sendall(self.greeting)

        while not self.stop_event.is_set():
            if self.drop_connection_event.is_set():
                break

            data = self.connection.recv(65536)
            self.requests.append(data)

            if self.drop_connection_event.is_set():
                break

            if self.delay_next_response > 0:
                time.sleep(self.delay_next_response)

            try:
                response = self.next_response()
            except IndexError:
                break

            self.connection.sendall(response)

            if data[:8] == b'STARTTLS':
                try:
                    self.wrap_socket()
                except OSError:
                    break

        if not self.drop_connection_event.is_set():
            try:
                self.connection.sendall(self.goodbye)
                self.connection.shutdown(socket.SHUT_RDWR)
            except TypeError:
                self.connection.shutdown()
            except (OSError, BrokenPipeError):
                pass

        try:
            self.connection.close()
        except (NameError, IOError):
            pass

    def run(self):
        try:
            self.socket = socket.socket()
            self.socket.bind((self.hostname, self.port))
            self.socket.listen(0)

            if self.port == 0:
                self.port = self.socket.getsockname()[1]

            self.ready.wait()
            while not self.stop_event.is_set():
                socket_ready, _, _ = select.select([self.socket], [], [], 0.1)
                if not socket_ready:
                    break
                self.connection, _ = self.socket.accept()
                if self.use_tls:
                    self.wrap_socket()
                self.handle_connection()

        finally:
            try:
                self.socket.close()
            except IOError:
                pass

    def stop(self):
        self.ready.abort()
        self.stop_event.set()
        self.join(0.1)


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

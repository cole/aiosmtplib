import threading
import socketserver
import socket
import ssl
import collections
import smtpd
import asyncore
from email.errors import HeaderParseError


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


class TestSMTPDChannel(smtpd.SMTPChannel):

    def _getaddr(self, arg):
        '''
        Don't raise an exception on unparsable email address
        '''
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
        asyncore.loop(0.01, True)

    def stop(self):
        self.smtpd.close()
        self.server_thread.join()

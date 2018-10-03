import asyncore
import smtpd
import threading
from email.errors import HeaderParseError


class TestSMTPDChannel(smtpd.SMTPChannel):
    def _getaddr(self, arg):
        """
        Don't raise an exception on unparsable email address
        """
        try:
            return super()._getaddr(arg)
        except HeaderParseError:
            return None, ""


class TestSMTPD(smtpd.SMTPServer):
    channel_class = TestSMTPDChannel

    def __init__(self, *args, **kwargs):
        if 'decode_data' not in kwargs:
            kwargs['decode_data'] = False
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

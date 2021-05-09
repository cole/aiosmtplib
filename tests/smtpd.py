"""
Implements handlers required on top of aiosmtpd for testing.
"""
import asyncio
import base64
import logging
import socket
import threading
from email.errors import HeaderParseError
from email.message import Message

from aiosmtpd.handlers import Message as MessageHandler
from aiosmtpd.smtp import MISSING
from aiosmtpd.smtp import SMTP as SMTPD

from aiosmtplib.sync import shutdown_loop


log = logging.getLogger("mail.log")


class RecordingHandler(MessageHandler):
    def __init__(self, messages_list, commands_list, responses_list):
        self.messages = messages_list
        self.commands = commands_list
        self.responses = responses_list
        super().__init__(message_class=Message)

    def record_command(self, command, *args):
        self.commands.append((command, *args))

    def record_server_response(self, status):
        self.responses.append(status)

    def handle_message(self, message):
        self.messages.append(message)

    async def handle_EHLO(self, server, session, envelope, hostname):
        """Advertise auth login support."""
        session.host_name = hostname
        if server._tls_protocol:
            return "250-AUTH LOGIN\r\n250 HELP"
        else:
            return "250 HELP"


class TestSMTPD(SMTPD):
    def _getaddr(self, arg):
        """
        Don't raise an exception on unparsable email address
        """
        try:
            return super()._getaddr(arg)
        except HeaderParseError:
            return None, ""

    async def _call_handler_hook(self, command, *args):
        self.event_handler.record_command(command, *args)
        return await super()._call_handler_hook(command, *args)

    async def push(self, status):
        result = await super().push(status)
        self.event_handler.record_server_response(status)

        return result

    async def smtp_EXPN(self, arg):
        """
        Pass EXPN to handler hook.
        """
        status = await self._call_handler_hook("EXPN")
        await self.push("502 EXPN not implemented" if status is MISSING else status)

    async def smtp_HELP(self, arg):
        """
        Override help to pass to handler hook.
        """
        status = await self._call_handler_hook("HELP")
        if status is MISSING:
            await super().smtp_HELP(arg)
        else:
            await self.push(status)

    async def smtp_STARTTLS(self, arg):
        """
        Override for uvloop compatibility.
        """
        self.event_handler.record_command("STARTTLS", arg)

        if arg:
            await self.push("501 Syntax: STARTTLS")
            return
        if not self.tls_context:
            await self.push("454 TLS not available")
            return
        await self.push("220 Ready to start TLS")
        # Create SSL layer.
        self._tls_protocol = asyncio.sslproto.SSLProtocol(
            self.loop, self, self.tls_context, None, server_side=True
        )
        self._original_transport = self.transport
        if hasattr(self._original_transport, "set_protocol"):
            self._original_transport.set_protocol(self._tls_protocol)
        else:
            self._original_transport._protocol = self._tls_protocol

        self.transport = self._tls_protocol._app_transport
        self._tls_protocol.connection_made(self._original_transport)

    async def smtp_AUTH(self, arg):
        self.event_handler.record_command("AUTH", arg)
        if not self._tls_protocol:
            await self.push("530 Must issue a STARTTLS command first.")
            return

        if arg[:5] == "LOGIN":
            await self.smtp_AUTH_LOGIN(arg[6:])
        else:
            await self.push("504 Unsupported AUTH mechanism.")

    async def smtp_AUTH_LOGIN(self, arg):
        username = base64.b64decode(arg)
        log.debug("SMTP AUTH LOGIN user: %s", username)
        await self.push("334 VXNlcm5hbWU6")
        encoded_password = await self._reader.readline()
        log.debug("SMTP AUTH LOGIN password: %s", encoded_password)
        password = base64.b64decode(encoded_password)

        if username == b"test" and password == b"test":
            await self.push("235 You're in!")
        else:
            await self.push("535 Nope.")


class SMTPDController:
    """
    Based on https://github.com/aio-libs/aiosmtpd/blob/master/aiosmtpd/controller.py,
    but we force IPv4.
    """

    def __init__(
        self,
        handler,
        loop=None,
        hostname=None,
        port=8025,
        *,
        ready_timeout=1.0,
        enable_SMTPUTF8=True,
        ssl_context=None
    ):
        self.handler = handler
        self.hostname = hostname
        self.port = port
        self.enable_SMTPUTF8 = enable_SMTPUTF8
        self.ssl_context = ssl_context
        self.loop = asyncio.new_event_loop() if loop is None else loop
        self.server = None
        self._thread = None
        self._thread_exception = None
        self.ready_timeout = ready_timeout

    def factory(self):
        """Allow subclasses to customize the handler/server creation."""
        return TestSMTPD(self.handler, enable_SMTPUTF8=self.enable_SMTPUTF8)

    def _run(self, ready_event):
        asyncio.set_event_loop(self.loop)
        try:
            self.server = self.loop.run_until_complete(
                self.loop.create_server(
                    self.factory,
                    host=self.hostname,
                    port=self.port,
                    ssl=self.ssl_context,
                    family=socket.AF_INET,
                )
            )
        except Exception as error:
            self._thread_exception = error
            return
        self.loop.call_soon(ready_event.set)
        self.loop.run_forever()
        self.server.close()
        self.loop.run_until_complete(self.server.wait_closed())
        self.server = None

    def start(self):
        ready_event = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready_event,))
        self._thread.daemon = True
        self._thread.start()
        # Wait a while until the server is responding.
        ready_event.wait(self.ready_timeout)
        if self._thread_exception is not None:
            raise self._thread_exception

    def _stop(self):
        self.loop.stop()
        shutdown_loop(self.loop)

    def stop(self):
        self.loop.call_soon_threadsafe(self._stop)
        self._thread.join()
        self._thread = None

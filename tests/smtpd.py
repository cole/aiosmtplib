"""
Implements handlers required on top of aiosmtpd for testing.
"""
import asyncio
import base64
import logging
from email.errors import HeaderParseError
from email.message import Message

from aiosmtpd.handlers import Message as MessageHandler
from aiosmtpd.smtp import MISSING
from aiosmtpd.smtp import SMTP as SMTPD


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
        return "250-AUTH LOGIN\r\n250 HELP"


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

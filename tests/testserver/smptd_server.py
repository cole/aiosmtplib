from email.errors import HeaderParseError
from email.message import Message

from aiosmtpd.handlers import Message as MessageHandler
from aiosmtpd.smtp import SMTP as SMTPD, MISSING


class RecordingHandler(MessageHandler):
    HELO_response_message = None
    EHLO_response_message = None
    NOOP_response_message = None
    QUIT_response_message = None
    VRFY_response_message = None
    MAIL_response_message = None
    RCPT_response_message = None
    DATA_response_message = None
    RSET_response_message = None
    EXPN_response_message = None
    HELP_response_message = None

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

        hook_response = await super()._call_handler_hook(command, *args)
        response_message = getattr(
            self.event_handler, command + "_response_message", None
        )

        return response_message or hook_response

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

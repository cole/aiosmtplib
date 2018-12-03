from email.errors import HeaderParseError
from email.message import Message

from aiosmtpd.handlers import Message as MessageHandler
from aiosmtpd.smtp import SMTP as SMTPD, MISSING


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

    async def handle_DATA(self, *args):
        self.record_command("DATA", *args)

        response = await super().handle_DATA(*args)
        return response

    async def handle_HELO(self, *args):
        self.record_command("HELO", *args)

        return MISSING

    async def handle_EHLO(self, *args):
        self.record_command("EHLO", *args)

        return MISSING

    async def handle_NOOP(self, *args):
        self.record_command("NOOP", *args)

        return MISSING

    async def handle_QUIT(self, *args):
        self.record_command("QUIT", *args)

        return MISSING

    async def handle_VRFY(self, *args):
        self.record_command("VRFY", *args)

        return MISSING

    async def handle_MAIL(self, *args):
        self.record_command("MAIL", *args)

        return MISSING

    async def handle_RCPT(self, *args):
        self.record_command("RCPT", *args)

        return MISSING

    async def handle_RSET(self, *args):
        self.record_command("RSET", *args)

        return MISSING

    async def handle_EXPN(self, *args):
        self.record_command("EXPN", *args)

        return MISSING


class TestSMTPD(SMTPD):
    def _getaddr(self, arg):
        """
        Don't raise an exception on unparsable email address
        """
        try:
            return super()._getaddr(arg)
        except HeaderParseError:
            return None, ""

    async def push(self, status):
        result = await super().push(status)
        self.event_handler.record_server_response(status)

        return result

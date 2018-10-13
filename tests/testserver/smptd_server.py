from email.errors import HeaderParseError
from email.message import Message

from aiosmtpd.handlers import Message as MessageHandler
from aiosmtpd.smtp import SMTP as SMTPD


class TestHandler(MessageHandler):
    def __init__(self, messages_list):
        self.messages = messages_list
        super().__init__(message_class=Message)

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

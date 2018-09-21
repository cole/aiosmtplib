from asyncio import TimeoutError
from typing import List


__all__ = (
    "SMTPAuthenticationError",
    "SMTPConnectError",
    "SMTPDataError",
    "SMTPException",
    "SMTPHeloError",
    "SMTPNotSupported",
    "SMTPRecipientRefused",
    "SMTPRecipientsRefused",
    "SMTPResponseException",
    "SMTPSenderRefused",
    "SMTPServerDisconnected",
    "SMTPTimeoutError",
)


class SMTPException(Exception):
    """
    Base class for all SMTP exceptions.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        self.args = (message,)


class SMTPServerDisconnected(SMTPException, ConnectionError):
    """
    The connection was lost unexpectedly, or a command was run that requires
    a connection.
    """

    pass


class SMTPConnectError(SMTPException, ConnectionError):
    """
    An error occurred while connecting to the SMTP server.
    """

    pass


class SMTPTimeoutError(SMTPException, TimeoutError):
    """
    A timeout occurred while performing a network operation.
    """

    pass


class SMTPResponseException(SMTPException):
    """
    Base class for all server responses with error codes.
    """

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        self.args = (code, message)


class SMTPNotSupported(SMTPResponseException):
    """
    A command or argument sent to the SMTP server is not supported.
    """

    pass


class SMTPHeloError(SMTPResponseException):
    """
    Server refused HELO or EHLO.
    """

    pass


class SMTPDataError(SMTPResponseException):
    """
    Server refused DATA content.
    """

    pass


class SMTPAuthenticationError(SMTPResponseException):
    """
    Server refused our AUTH request; may be caused by invalid credentials.
    """

    pass


class SMTPSenderRefused(SMTPResponseException):
    """
    SMTP server refused the message sender.
    """

    def __init__(self, code: int, message: str, sender: str) -> None:
        self.code = code
        self.message = message
        self.sender = sender
        self.args = (code, message, sender)


class SMTPRecipientRefused(SMTPResponseException):
    """
    SMTP server refused a message recipient.
    """

    def __init__(self, code: int, message: str, recipient: str) -> None:
        self.code = code
        self.message = message
        self.recipient = recipient
        self.args = (code, message, recipient)


class SMTPRecipientsRefused(SMTPException):
    """
    SMTP server refused multiple recipients.
    """

    def __init__(self, recipients: List[SMTPRecipientRefused]) -> None:
        self.recipients = recipients
        self.args = (recipients,)

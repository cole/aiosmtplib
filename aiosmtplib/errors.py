"""
Exception classes.

Unlinke in standard smtplib, these do not inherit from OSError.
"""


class SMTPException(Exception):
    """
    Base class for all SMTP exceptions.
    """
    def __init__(self, message):
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
    An error occurred while connectiong to the SMTP server.
    """
    pass


class SMTPResponseException(SMTPException):
    """
    Base class for all server responses with error codes.
    """
    def __init__(self, code, message):
        self.code = code
        self.message = message
        self.args = (code, message,)


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
    Server refused our AUTH request, probably due to bad login information.
    """
    pass


class SMTPSenderRefused(SMTPResponseException):
    """
    SMTP server refused the message sender.
    """
    def __init__(self, code, message, sender):
        self.code = code
        self.message = message
        self.sender = sender
        self.args = (code, message, sender,)


class SMTPRecipientRefused(SMTPResponseException):
    """
    SMTP server refused a message recipient.
    """
    def __init__(self, code, message, recipient):
        self.code = code
        self.message = message
        self.recipient = recipient
        self.args = (code, message, recipient,)


class SMTPRecipientsRefused(SMTPException):
    """
    Wraps a list of SMTPRecipientRefused exceptions.
    """
    def __init__(self, recipients):
        self.recipients = recipients
        self.args = (recipients,)

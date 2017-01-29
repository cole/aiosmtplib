"""
aiomsmtplib.smtp
================

The SMTP class is the public API for aiosmtplib.

Basic usage:
    loop = asyncio.get_event_loop()
    smtp = aiosmtplib.SMTP(hostname='localhost', port=1025, loop=loop)
    send_coroutine = smtp.sendmail(
        'root@localhost', ['somebody@localhost'], "Hello World")
    asyncio.run_until_complete(smtp.connect())
    asyncio.run_until_complete(send_coroutine)

"""

import asyncio
from email.message import Message
from typing import Any, Dict, Iterable, List, Tuple, Union

from aiosmtplib.auth import SMTPAuth
from aiosmtplib.email import flatten_message
from aiosmtplib.errors import (
    SMTPRecipientRefused, SMTPRecipientsRefused, SMTPResponseException,
    SMTPTimeoutError,
)
from aiosmtplib.response import SMTPResponse


__all__ = ('SMTP',)

RecipientsType = Union[str, Iterable[str]]
RecipientErrorsType = Dict[str, SMTPResponse]
SendmailResponseType = Tuple[RecipientErrorsType, str]


class SMTP(SMTPAuth):
    """
    SMTP client class.

    Actual implementation is split into the following classes:
    `SMTPAuth` - login and authentication methods
    `ESMTP` - SMTP/ESMTP command support
    `SMTPConnection` - connection handling
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._command_lock = asyncio.Lock(loop=self.loop)

    async def __aenter__(self) -> 'SMTP':
        if not self.is_connected:
            await self.connect()

        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        connection_errors = (ConnectionError, SMTPTimeoutError)
        if exc_type in connection_errors or not self.is_connected:
            self.close()
        else:
            try:
                await self.quit()
            except connection_errors:
                self.close()

    async def sendmail(
            self, sender: str, recipients: RecipientsType,
            message: Union[str, bytes], mail_options: Iterable[str] = None,
            rcpt_options: Iterable[str] = None, **kwargs) -> \
            SendmailResponseType:
        """
        This command performs an entire mail transaction.

        The arguments are:
            - sender       : The address sending this mail.
            - recipients   : A list of addresses to send this mail to.  A bare
                             string will be treated as a list with 1 address.
            - message      : The message string to send.
            - mail_options : List of options (such as ESMTP 8bitmime) for the
                             mail command.
            - rcpt_options : List of options (such as DSN commands) for
                             all the rcpt commands.

        message must be a string containing characters in the ASCII range.
        The string is encoded to bytes using the ascii codec, and lone \\r and
        \\n characters are converted to \\r\\n characters.

        If there has been no previous HELO or EHLO command this session, this
        method tries EHLO first.

        This method will return normally if the mail is accepted for at least
        one recipient.  It returns a tuple consisting of:

            - an error dictionary, with one entry for each
                recipient that was refused.  Each entry contains a tuple of the
                SMTP error code and the accompanying error message sent by the
                server.
            - the message sent by the server in response to the DATA command
                (often containing a message id)


        Example usage:..

             >>> import asyncio
             >>> import aiosmtplib
             >>> loop = asyncio.get_event_loop()
             >>> smtp = aiosmtplib.SMTP(hostname='localhost', port=25)
             >>> loop.run_until_complete(smtp.connect())
             >>> recipients = ['one@one.org', 'two@two.org','nobody@three.org']
             >>> message = 'From: Me@my.org\nSubject: testing...\nHello World'
             >>> loop.run_until_complete(
             >>>     smtp.sendmail('me@my.org', recipients, message))
             (
                 {
                    'nobody@three.org': (550 ,'User unknown'),
                 },
                 'Written safely to disk. #902487694.289148.12219.',
             )
             >>> loop.run_until_complete(smtp.quit())

        In the above example, the message was accepted for delivery to two
        of the three addresses, and one was rejected, with the error code
        550.  If all addresses are accepted, then the method will return an
        empty errors dictionary.

        If an SMTPResponseException is raised by this method, we try to send
        an RSET command to reset the server envelope automatically for the next
        attempt.
        """
        if isinstance(recipients, str):
            recipients = [recipients]
        else:
            recipients = list(recipients)

        if mail_options is None:
            mail_options = []
        else:
            mail_options = list(mail_options)

        if rcpt_options is None:
            rcpt_options = []
        else:
            rcpt_options = list(rcpt_options)

        async with self._command_lock:
            await self._ehlo_or_helo_if_needed()

            if self.supports_extension('size'):
                size_option = 'size={}'.format(len(message))
                mail_options.append(size_option)

            try:
                await self.mail(sender, options=mail_options, **kwargs)
                recipient_errors = await self._send_recipients(
                    recipients, options=rcpt_options, **kwargs)
                response = await self.data(message, **kwargs)
            except (SMTPResponseException, SMTPRecipientsRefused) as exc:
                # If we got an error, reset the envelope.
                try:
                    await self.rset(**kwargs)
                except (ConnectionError, SMTPResponseException):
                    # If we're disconnected on the reset, or we get a bad
                    # status, don't raise that as it's confusing
                    pass
                raise exc

        return recipient_errors, response.message

    async def _send_recipients(
            self, recipients: List[str], options: List[str] = None,
            **kwargs) -> RecipientErrorsType:
        """
        Send the recipients given to the server. Used as part of ``sendmail``.
        """
        recipient_errors = []
        for address in recipients:
            try:
                await self.rcpt(address, **kwargs)
            except SMTPRecipientRefused as exc:
                recipient_errors.append(exc)

        if len(recipient_errors) == len(recipients):
            raise SMTPRecipientsRefused(recipient_errors)

        formatted_errors = {
            err.recipient: SMTPResponse(err.code, err.message)
            for err in recipient_errors
        }

        return formatted_errors

    async def send_message(
            self, message: Message, sender: str = None,
            recipients: RecipientsType = None,
            mail_options: Iterable[str] = None,
            rcpt_options: Iterable[str] = None, **kwargs) -> \
            SendmailResponseType:
        """
        Converts an ``email.message.Message`` object to a string and
        passes it to sendmail.

        The arguments are as for ``sendmail``, except that messsage is an
        ``email.message.Message`` object.  If sender is None or recipients is
        None, these arguments are taken from the headers of the Message as
        described in RFC 2822 (a ValueError is raised if there is more than
        one set of 'Resent-' headers).  Regardless of the values of sender and
        recipients, any Bcc field (or Resent-Bcc field, when the Message is a
        resent) of the Message object won't be transmitted.  The Message
        object is then serialized using ``email.generator.Generator`` and
        ``sendmail`` is called to transmit the message.

        'Resent-Date' is a mandatory field if the Message is resent (RFC 2822
        Section 3.6.6). In such a case, we use the 'Resent-*' fields.
        However, if there is more than one 'Resent-' block there's no way to
        unambiguously determine which one is the most recent in all cases,
        so rather than guess we raise a ``ValueError`` in that case.
        """
        header_sender, header_recipients, flat_message = flatten_message(
            message)

        if sender is None:
            sender = header_sender
        if recipients is None:
            recipients = header_recipients

        result = await self.sendmail(
            sender, recipients, flat_message, **kwargs)

        return result

    def _run_sync(self, method, *args, **kwargs) -> Any:
        assert not self.loop.is_running(), 'Event loop is already running'

        if not self.is_connected:
            self.loop.run_until_complete(self.connect())

        coro = getattr(self, method)
        result = self.loop.run_until_complete(coro(*args, **kwargs))

        if self.is_connected:
            self.loop.run_until_complete(self.quit())

        return result

    def sendmail_sync(self, *args, **kwargs) -> SendmailResponseType:
        return self._run_sync('sendmail', *args, **kwargs)

    def send_message_sync(self, *args, **kwargs) -> SendmailResponseType:
        return self._run_sync('send_message', *args, **kwargs)

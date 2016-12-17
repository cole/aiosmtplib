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
import email.message
from typing import Dict, List, Union

from aiosmtplib.email import flatten_message
from aiosmtplib.errors import (
    SMTPAuthenticationError, SMTPException, SMTPRecipientRefused,
    SMTPRecipientsRefused, SMTPResponseException, SMTPTimeoutError,
)
from aiosmtplib.esmtp import ESMTP
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus
from aiosmtplib.typing import OptionalDefaultNumber, SendmailResponse, _default

__all__ = ('SMTP',)


class SMTP(ESMTP):
    """
    SMTP connection client class.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.sendmail_lock = asyncio.Lock(loop=self.loop)

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
            except (ConnectionError, SMTPTimeoutError):
                self.close()

    async def login(
            self, username: str, password: str,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        SMTP Login command. Tries all supported auth methods in order.
        """
        self._raise_error_if_disconnected()
        await self._ehlo_or_helo_if_needed()

        if not self.supports_extension('auth'):
            raise SMTPException('SMTP AUTH extension not supported by server.')

        # Some servers advertise authentication methods they don't really
        # support, so if authentication fails, we continue until we've tried
        # all methods.
        response = None
        for auth_name, auth_method in self.supported_auth_methods:
            response = await self.auth(
                auth_method, username, password, timeout=timeout)

            if response.code == SMTPStatus.auth_successful:
                break
        else:
            if response is None:
                raise SMTPException('No suitable authentication method found.')
            else:
                raise SMTPAuthenticationError(response.code, response.message)

        return response

    async def sendmail(
            self, sender: str, recipients: Union[str, List[str]],
            message: str, mail_options: List[str] = None,
            rcpt_options: List[str] = None,
            timeout: OptionalDefaultNumber = _default) -> SendmailResponse:
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


        This method may raise the following exceptions:

         SMTPHeloError          The server didn't reply properly to
                                the helo greeting.
         SMTPRecipientsRefused  The server rejected ALL recipients
                                (no mail was sent).
         SMTPSenderRefused      The server didn't accept the from_addr.
         SMTPDataError          The server replied with an unexpected
                                error code (other than a refusal of
                                a recipient).

        Note: the connection will be open even after an exception is raised.


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
        if mail_options is None:
            mail_options = []
        if rcpt_options is None:
            rcpt_options = []

        async with self.sendmail_lock:
            await self._ehlo_or_helo_if_needed()

            if self.supports_extension('size'):
                size_option = 'size={}'.format(len(message))
                mail_options.append(size_option)

            try:
                await self.mail(sender, options=mail_options, timeout=timeout)
            except SMTPResponseException as exc:
                await self._silent_rset(timeout=timeout)
                raise exc

            recipient_errors = await self._send_recipients(
                recipients, options=rcpt_options, timeout=timeout)

            try:
                response = await self.data(message, timeout=timeout)
            except SMTPResponseException as exc:
                await self._silent_rset(timeout=timeout)
                raise exc

        return recipient_errors, response.message

    async def _send_recipients(
            self, recipients: List[str], options: List[str] = None,
            timeout: OptionalDefaultNumber = _default) -> \
            Dict[str, SMTPResponse]:
        recipient_errors = []
        for address in recipients:
            try:
                await self.rcpt(
                    address, options=options, timeout=timeout)
            except SMTPRecipientRefused as exc:
                recipient_errors.append(exc)

        if len(recipient_errors) == len(recipients):
            await self._silent_rset(timeout=timeout)
            raise SMTPRecipientsRefused(recipient_errors)

        formatted_errors = {
            err.recipient: SMTPResponse(err.code, err.message)
            for err in recipient_errors
        }

        return formatted_errors

    async def _silent_rset(self, timeout: OptionalDefaultNumber = _default):
        """
        Clear the server envelope without raising any errors.
        Used if we fail partway through sendmail, so that the next sendmail
        call will work.
        """
        try:
            await self.rset(timeout=timeout)
        except (ConnectionError, SMTPResponseException):
            # If we're disconnected on the reset, or we get a bad status,
            # don't raise that as it's confusing
            pass

    async def send_message(
            self, message: email.message.Message, sender: str = None,
            recipients: Union[str, List[str]] = None,
            mail_options: List[str] = None, rcpt_options: List[str] = None,
            timeout: OptionalDefaultNumber = _default) -> SendmailResponse:
        """
        Converts message to a bytestring and passes it to sendmail.

        The arguments are as for sendmail, except that messsage is an
        email.message.Message object.  If sender is None or recipients is
        None, these arguments are taken from the headers of the Message as
        described in RFC 2822 (a ValueError is raised if there is more than
        one set of 'Resent-' headers).  Regardless of the values of sender and
        recipients, any Bcc field (or Resent-Bcc field, when the Message is a
        resent) of the Message object won't be transmitted.  The Message
        object is then serialized using email.generator.BytesGenerator and
        sendmail is called to transmit the message.

        'Resent-Date' is a mandatory field if the Message is resent (RFC 2822
        Section 3.6.6). In such a case, we use the 'Resent-*' fields.
        However, if there is more than one 'Resent-' block there's no way to
        unambiguously determine which one is the most recent in all cases,
        so rather than guess we raise a ValueError in that case.
        """
        header_sender, header_recipients, flat_message = flatten_message(
            message)

        if sender is None:
            sender = header_sender
        if recipients is None:
            recipients = header_recipients

        result = await self.sendmail(
            sender, recipients, flat_message, mail_options=mail_options,
            rcpt_options=rcpt_options, timeout=timeout)

        return result

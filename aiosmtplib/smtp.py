"""
Main SMTP client class.

Implementation is split into the following parent classes:

    * :class:`.auth.SMTPAuth` - login and authentication methods
    * :class:`.esmtp.ESMTP` - ESMTP command support
    * :class:`.connection.SMTPConnection` - connection handling
"""
import asyncio
import email.message
from typing import Dict, Iterable, Optional, Sequence, Tuple, Union

from .auth import SMTPAuth
from .connection import SMTPConnection
from .default import Default, _default
from .email import extract_recipients, extract_sender, flatten_message
from .errors import (
    SMTPNotSupported,
    SMTPRecipientRefused,
    SMTPRecipientsRefused,
    SMTPResponseException,
)
from .response import SMTPResponse
from .sync import async_to_sync


__all__ = ("SMTP",)


class SMTP(SMTPAuth):
    """
    Main SMTP client class.

    Basic usage:

        >>> loop = asyncio.get_event_loop()
        >>> smtp = aiosmtplib.SMTP(hostname="127.0.0.1", port=1025)
        >>> loop.run_until_complete(smtp.connect())
        (220, ...)
        >>> sender = "root@localhost"
        >>> recipients = ["somebody@localhost"]
        >>> message = "Hello World"
        >>> send = smtp.sendmail(sender, recipients, "Hello World")
        >>> loop.run_until_complete(send)
        ({}, 'OK')
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._sendmail_lock = None  # type: Optional[asyncio.Lock]

    # Hack to make Sphinx find the SMTPConnection docstring
    __init__.__doc__ = SMTPConnection.__init__.__doc__

    async def sendmail(
        self,
        sender: str,
        recipients: Union[str, Sequence[str]],
        message: Union[str, bytes],
        mail_options: Optional[Iterable[str]] = None,
        rcpt_options: Optional[Iterable[str]] = None,
        timeout: Optional[Union[float, Default]] = _default,
    ) -> Tuple[Dict[str, SMTPResponse], str]:
        """
        This command performs an entire mail transaction.

        The arguments are:
            - sender: The address sending this mail.
            - recipients: A list of addresses to send this mail to.  A bare
                string will be treated as a list with 1 address.
            - message: The message string to send.
            - mail_options: List of options (such as ESMTP 8bitmime) for the
                MAIL command.
            - rcpt_options: List of options (such as DSN commands) for all the
                RCPT commands.

        message must be a string containing characters in the ASCII range.
        The string is encoded to bytes using the ascii codec, and lone \\\\r
        and \\\\n characters are converted to \\\\r\\\\n characters.

        If there has been no previous HELO or EHLO command this session, this
        method tries EHLO first.

        This method will return normally if the mail is accepted for at least
        one recipient.  It returns a tuple consisting of:

            - an error dictionary, with one entry for each recipient that was
                refused.  Each entry contains a tuple of the SMTP error code
                and the accompanying error message sent by the server.
            - the message sent by the server in response to the DATA command
                (often containing a message id)

        Example:

             >>> loop = asyncio.get_event_loop()
             >>> smtp = aiosmtplib.SMTP(hostname="127.0.0.1", port=1025)
             >>> loop.run_until_complete(smtp.connect())
             (220, ...)
             >>> recipients = ["one@one.org", "two@two.org", "3@three.org"]
             >>> message = "From: Me@my.org\\nSubject: testing\\nHello World"
             >>> send_coro = smtp.sendmail("me@my.org", recipients, message)
             >>> loop.run_until_complete(send_coro)
             ({}, 'OK')
             >>> loop.run_until_complete(smtp.quit())
             (221, Bye)

        In the above example, the message was accepted for delivery for all
        three addresses. If delivery had been only successful to two
        of the three addresses, and one was rejected, the response would look
        something like::

            (
                {"nobody@three.org": (550, "User unknown")},
                "Written safely to disk. #902487694.289148.12219.",
            )


        If delivery is not successful to any addresses,
        :exc:`.SMTPRecipientsRefused` is raised.

        If :exc:`.SMTPResponseException` is raised by this method, we try to
        send an RSET command to reset the server envelope automatically for
        the next attempt.

        :raises SMTPRecipientsRefused: delivery to all recipients failed
        :raises SMTPResponseException: on invalid response
        """
        if isinstance(recipients, str):
            recipients = [recipients]
        if mail_options is None:
            mail_options = []
        else:
            mail_options = list(mail_options)
        if rcpt_options is None:
            rcpt_options = []
        else:
            rcpt_options = list(rcpt_options)

        if any(option.lower() == "smtputf8" for option in mail_options):
            mailbox_encoding = "utf-8"
        else:
            mailbox_encoding = "ascii"

        if self._sendmail_lock is None:
            self._sendmail_lock = asyncio.Lock()

        async with self._sendmail_lock:
            # Make sure we've done an EHLO for extension checks
            await self._ehlo_or_helo_if_needed()

            if mailbox_encoding == "utf-8" and not self.supports_extension("smtputf8"):
                raise SMTPNotSupported("SMTPUTF8 is not supported by this server")

            if self.supports_extension("size"):
                size_option = "size={}".format(len(message))
                mail_options.insert(0, size_option)

            try:
                await self.mail(
                    sender,
                    options=mail_options,
                    encoding=mailbox_encoding,
                    timeout=timeout,
                )
                recipient_errors = await self._send_recipients(
                    recipients, rcpt_options, encoding=mailbox_encoding, timeout=timeout
                )
                response = await self.data(message, timeout=timeout)
            except (SMTPResponseException, SMTPRecipientsRefused) as exc:
                # If we got an error, reset the envelope.
                try:
                    await self.rset(timeout=timeout)
                except (ConnectionError, SMTPResponseException):
                    # If we're disconnected on the reset, or we get a bad
                    # status, don't raise that as it's confusing
                    pass
                raise exc

        return recipient_errors, response.message

    async def _send_recipients(
        self,
        recipients: Sequence[str],
        options: Iterable[str],
        encoding: str = "ascii",
        timeout: Optional[Union[float, Default]] = _default,
    ) -> Dict[str, SMTPResponse]:
        """
        Send the recipients given to the server. Used as part of
        :meth:`.sendmail`.
        """
        recipient_errors = []
        for address in recipients:
            try:
                await self.rcpt(
                    address, options=options, encoding=encoding, timeout=timeout
                )
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
        self,
        message: Union[email.message.EmailMessage, email.message.Message],
        sender: Optional[str] = None,
        recipients: Optional[Union[str, Sequence[str]]] = None,
        mail_options: Optional[Iterable[str]] = None,
        rcpt_options: Optional[Iterable[str]] = None,
        timeout: Optional[Union[float, Default]] = _default,
    ) -> Tuple[Dict[str, SMTPResponse], str]:
        r"""
        Sends an :py:class:`email.message.EmailMessage` object.

        Arguments are as for :meth:`.sendmail`, except that message is an
        :py:class:`email.message.EmailMessage` object.  If sender is None or
        recipients is None, these arguments are taken from the headers of the
        EmailMessage as described in RFC 2822.  Regardless of the values of sender
        and recipients, any Bcc field (or Resent-Bcc field, when the message is a
        resent) of the EmailMessage object will not be transmitted.  The EmailMessage
        object is then serialized using :py:class:`email.generator.Generator` and
        :meth:`.sendmail` is called to transmit the message.

        'Resent-Date' is a mandatory field if the message is resent (RFC 2822
        Section 3.6.6). In such a case, we use the 'Resent-\*' fields.
        However, if there is more than one 'Resent-' block there's no way to
        unambiguously determine which one is the most recent in all cases,
        so rather than guess we raise a ``ValueError`` in that case.

        :raises ValueError:
            on more than one Resent header block
            on no sender kwarg or From header in message
            on no recipients kwarg or To, Cc or Bcc header in message
        :raises SMTPRecipientsRefused: delivery to all recipients failed
        :raises SMTPResponseException: on invalid response
        """
        if mail_options is None:
            mail_options = []
        else:
            mail_options = list(mail_options)

        if sender is None:
            sender = extract_sender(message)
        if sender is None:
            raise ValueError("No From header provided in message")

        if isinstance(recipients, str):
            recipients = [recipients]
        elif recipients is None:
            recipients = extract_recipients(message)
        if not recipients:
            raise ValueError("No recipient headers provided in message")

        # Make sure we've done an EHLO for extension checks
        await self._ehlo_or_helo_if_needed()

        try:
            sender.encode("ascii")
            "".join(recipients).encode("ascii")
        except UnicodeEncodeError:
            utf8_required = True
        else:
            utf8_required = False

        if utf8_required:
            if not self.supports_extension("smtputf8"):
                raise SMTPNotSupported(
                    "An address containing non-ASCII characters was provided, but "
                    "SMTPUTF8 is not supported by this server"
                )
            elif "smtputf8" not in [option.lower() for option in mail_options]:
                mail_options.append("SMTPUTF8")

        if self.supports_extension("8BITMIME"):
            if "body=8bitmime" not in [option.lower() for option in mail_options]:
                mail_options.append("BODY=8BITMIME")
            cte_type = "8bit"
        else:
            cte_type = "7bit"

        flat_message = flatten_message(message, utf8=utf8_required, cte_type=cte_type)

        return await self.sendmail(
            sender,
            recipients,
            flat_message,
            mail_options=mail_options,
            rcpt_options=rcpt_options,
            timeout=timeout,
        )

    def sendmail_sync(self, *args, **kwargs) -> Tuple[Dict[str, SMTPResponse], str]:
        """
        Synchronous version of :meth:`.sendmail`. This method starts
        the event loop to connect, send the message, and disconnect.
        """

        async def sendmail_coroutine():
            async with self:
                result = await self.sendmail(*args, **kwargs)

            return result

        return async_to_sync(sendmail_coroutine(), loop=self.loop)

    def send_message_sync(self, *args, **kwargs) -> Tuple[Dict[str, SMTPResponse], str]:
        """
        Synchronous version of :meth:`.send_message`. This method
        starts the event loop to connect, send the message, and disconnect.
        """

        async def send_message_coroutine():
            async with self:
                result = await self.send_message(*args, **kwargs)

            return result

        return async_to_sync(send_message_coroutine(), loop=self.loop)

"""
Public API.

Implementation is split into the following classes:

    * :class:`.auth.SMTPAuth` - login and authentication methods
    * :class:`.esmtp.ESMTP` - ESMTP command support
    * :class:`.connection.SMTPConnection` - connection handling
"""
import asyncio
import ssl
from email.message import Message
from typing import Dict, Iterable, List, Tuple, Union

from .auth import SMTPAuth
from .compat import get_running_loop
from .connection import SMTPConnection
from .default import Default, _default
from .email import flatten_message
from .errors import SMTPRecipientRefused, SMTPRecipientsRefused, SMTPResponseException
from .response import SMTPResponse
from .sync import async_to_sync


__all__ = ("SMTP", "send_message")


DefaultNumType = Union[float, int, Default]
RecipientsType = Union[str, Iterable[str]]
RecipientErrorsType = Dict[str, SMTPResponse]
SendmailResponseType = Tuple[RecipientErrorsType, str]


class SMTP(SMTPAuth):
    """
    Main SMTP client class.

    Basic usage:

        >>> loop = asyncio.get_event_loop()
        >>> smtp = aiosmtplib.SMTP(hostname="127.0.0.1", port=1025, loop=loop)
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

        self._sendmail_lock = asyncio.Lock(loop=self.loop)

    # Hack to make Sphinx find the SMTPConnection docstring
    __init__.__doc__ = SMTPConnection.__init__.__doc__

    async def sendmail(
        self,
        sender: str,
        recipients: RecipientsType,
        message: Union[str, bytes],
        mail_options: Iterable[str] = None,
        rcpt_options: Iterable[str] = None,
        timeout: DefaultNumType = _default,
    ) -> SendmailResponseType:
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

        async with self._sendmail_lock:
            if self.supports_extension("size"):
                size_option = "size={}".format(len(message))
                mail_options.append(size_option)

            try:
                await self.mail(sender, options=mail_options, timeout=timeout)
                recipient_errors = await self._send_recipients(
                    recipients, options=rcpt_options, timeout=timeout
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
        recipients: List[str],
        options: List[str] = None,
        timeout: DefaultNumType = _default,
    ) -> RecipientErrorsType:
        """
        Send the recipients given to the server. Used as part of
        :meth:`.sendmail`.
        """
        recipient_errors = []
        for address in recipients:
            try:
                await self.rcpt(address, timeout=timeout)
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
        message: Message,
        sender: str = None,
        recipients: RecipientsType = None,
        mail_options: Iterable[str] = None,
        rcpt_options: Iterable[str] = None,
        timeout: DefaultNumType = _default,
    ) -> SendmailResponseType:
        r"""
        Sends an :class:`email.message.Message` object.

        Arguments are as for :meth:`.sendmail`, except that message is an
        :class:`email.message.Message` object.  If sender is None or recipients
        is None, these arguments are taken from the headers of the Message as
        described in RFC 2822.  Regardless of the values of sender and
        recipients, any Bcc field (or Resent-Bcc field, when the Message is a
        resent) of the Message object will not be transmitted.  The Message
        object is then serialized using :class:`email.generator.Generator` and
        :meth:`.sendmail` is called to transmit the message.

        'Resent-Date' is a mandatory field if the Message is resent (RFC 2822
        Section 3.6.6). In such a case, we use the 'Resent-\*' fields.
        However, if there is more than one 'Resent-' block there's no way to
        unambiguously determine which one is the most recent in all cases,
        so rather than guess we raise a ``ValueError`` in that case.

        :raises ValueError: on more than one Resent header block
        :raises SMTPRecipientsRefused: delivery to all recipients failed
        :raises SMTPResponseException: on invalid response
        """
        header_sender, header_recipients, flat_message = flatten_message(message)

        if sender is None:
            sender = header_sender
        if recipients is None:
            recipients = header_recipients

        result = await self.sendmail(sender, recipients, flat_message, timeout=timeout)

        return result

    def sendmail_sync(
        self,
        sender: str,
        recipients: RecipientsType,
        message: Union[str, bytes],
        mail_options: Iterable[str] = None,
        rcpt_options: Iterable[str] = None,
        timeout: DefaultNumType = _default,
    ) -> SendmailResponseType:
        """
        Synchronous version of :meth:`.sendmail`. This method starts
        the event loop to connect, send the message, and disconnect.
        """

        async def sendmail_coroutine():
            if not self.is_connected:
                await self.connect()
            try:
                result = await self.sendmail(
                    sender,
                    recipients,
                    message,
                    mail_options=mail_options,
                    rcpt_options=rcpt_options,
                    timeout=timeout,
                )
            finally:
                await self.quit()

            return result

        return async_to_sync(sendmail_coroutine(), loop=self.loop)

    def send_message_sync(
        self,
        message: Message,
        sender: str = None,
        recipients: RecipientsType = None,
        mail_options: Iterable[str] = None,
        rcpt_options: Iterable[str] = None,
        timeout: DefaultNumType = _default,
    ) -> SendmailResponseType:
        """
        Synchronous version of :meth:`.send_message`. This method
        starts the event loop to connect, send the message, and disconnect.
        """

        async def send_message_coroutine():
            if not self.is_connected:
                await self.connect()
            try:
                result = await self.send_message(
                    message,
                    sender=sender,
                    recipients=recipients,
                    mail_options=mail_options,
                    rcpt_options=rcpt_options,
                    timeout=timeout,
                )
            finally:
                await self.quit()

            return result

        return async_to_sync(send_message_coroutine(), loop=self.loop)


async def send_message(
    hostname: str,
    message: Union[Message, str, bytes],
    sender: str = None,
    recipients: RecipientsType = None,
    mail_options: Iterable[str] = None,
    rcpt_options: Iterable[str] = None,
    timeout: DefaultNumType = _default,
    port: int = None,
    source_address: str = None,
    use_tls: bool = False,
    validate_certs: bool = True,
    client_cert: str = None,
    client_key: str = None,
    tls_context: ssl.SSLContext = None,
    cert_bundle: str = None,
):
    """
    Send an email message. On await, connects to the SMTP server using the details
    provided, sends the message, then disconnects.

    :param hostname: Server name (or IP) to connect to
    :param message:  Message text. Either an :class:``email.message.Message`` object,
        ``str`` or ``bytes``. If a ``Message`` object is provided, sender and
        recipients set in the message headers will be used, unless overridden by
        the respective keyword arguments.

    :keyword sender:  From email address. If none, taken from the ``Message``.
    :keyword recipients: Recipient email addresses. If none, taken from the
        ``Message``.
    :keyword mail_options: Options (such as ESMTP 8bitmime) for the MAIL command.
    :keyword rcpt_options: Options (such as DSN commands) for all RCPT commands.

    :keyword port: Server port. Defaults to 25 if ``use_tls`` is
        False, 465 if ``use_tls`` is True.
    :keyword source_address: The hostname of the client. Defaults to the
        result of :func:`socket.getfqdn`. Note that this call blocks.
    :keyword timeout: Default timeout value for the connection, in seconds.
        Defaults to 60.
    :keyword use_tls: If True, make the initial connection to the server
        over TLS/SSL. Note that if the server supports STARTTLS only, this
        should be False.
    :keyword validate_certs: Determines if server certificates are
        validated. Defaults to True.
    :keyword client_cert: Path to client side certificate, for TLS.
    :keyword client_key: Path to client side key, for TLS.
    :keyword tls_context: An existing :class:`ssl.SSLContext`, for TLS.
        Mutually exclusive with ``client_cert``/``client_key``.
    :keyword cert_bundle: Path to certificate bundle, for TLS verification.

    :raises ValueError: mutually exclusive options provided
    """
    loop = get_running_loop()
    client = SMTP(
        loop=loop,
        hostname=hostname,
        port=port,
        source_address=source_address,
        use_tls=use_tls,
        validate_certs=validate_certs,
        client_cert=client_cert,
        client_key=client_key,
        tls_context=tls_context,
        cert_bundle=cert_bundle,
    )

    await client.connect(timeout=timeout)
    await client._ehlo_or_helo_if_needed()

    try:
        if isinstance(message, Message):
            result = await client.send_message(
                message,
                sender=sender,
                recipients=recipients,
                mail_options=mail_options,
                rcpt_options=rcpt_options,
                timeout=timeout,
            )
        else:
            if recipients is None:
                raise ValueError("Recipients must be provided with raw messages.")
            if sender is None:
                raise ValueError("Sender must be provided with raw messages.")

            result = await client.sendmail(
                sender,
                recipients,
                message,
                mail_options=mail_options,
                rcpt_options=rcpt_options,
                timeout=timeout,
            )
    finally:
        await client.quit()

    return result

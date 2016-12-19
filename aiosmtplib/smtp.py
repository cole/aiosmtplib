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
from typing import Dict, Iterable, List, Tuple, Union

from aiosmtplib.auth import AUTH_METHODS
from aiosmtplib.connection import SMTPConnection
from aiosmtplib.email import flatten_message, parse_address, quote_address
from aiosmtplib.errors import (
    SMTPAuthenticationError, SMTPDataError, SMTPException, SMTPHeloError,
    SMTPRecipientRefused, SMTPRecipientsRefused, SMTPResponseException,
    SMTPSenderRefused, SMTPTimeoutError,
)
from aiosmtplib.esmtp import parse_esmtp_extensions
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus
from aiosmtplib.typing import (
    AuthFunctionType, OptionalDefaultNumber, OptionalDefaultSSLContext,
    OptionalDefaultStr, SendmailResponse, _default,
)

__all__ = ('SMTP',)


class SMTP(SMTPConnection):
    """
    SMTP client class.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.last_helo_response = None  # type: SMTPResponse
        self._last_ehlo_response = None  # type: SMTPResponse
        self.esmtp_extensions = {}  # type: Dict[str, str]
        self.supports_esmtp = False  # type: bool
        self.server_auth_methods = []  # type: List[str]
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
            except connection_errors:
                self.close()

    @property
    def last_ehlo_response(self) -> SMTPResponse:
        return self._last_ehlo_response

    @last_ehlo_response.setter
    def last_ehlo_response(self, response: SMTPResponse) -> None:
        """
        When setting the last EHLO response, parse the message for supported
        extensions and auth methods.
        """
        extensions, auth_methods = parse_esmtp_extensions(response.message)
        self._last_ehlo_response = response
        self.esmtp_extensions = extensions
        self.server_auth_methods = auth_methods
        self.supports_esmtp = True

    @property
    def is_ehlo_or_helo_needed(self) -> bool:
        """
        Check if we've already recieved a response to an EHLO or HELO command.
        """
        return (
            self.last_ehlo_response is None and
            self.last_helo_response is None)

    @property
    def supported_auth_methods(self) -> List[Tuple[str, AuthFunctionType]]:
        """
        Get all AUTH methods supported by the server and by us.
        Returns a list of (auth_name, auth_function) tuples.
        """
        return [
            auth for auth in AUTH_METHODS
            if auth[0] in self.server_auth_methods
        ]

    async def execute_command(
            self, *args: str,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Check that we're connected, if we got a timeout value, and then
        pass the command to the protocol.
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore

        self._raise_error_if_disconnected()

        return await self.protocol.execute_command(  # type: ignore
            *args, timeout=timeout)

    # base SMTP commands - defined in RFC 821 #

    async def helo(
            self, hostname: str = None,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send the SMTP HELO command.
        Hostname to send for this command defaults to the FQDN of the local
        host.

        Raises ``SMTPHeloError`` on an unexpected server response code.
        """
        if hostname is None:
            hostname = self.source_address

        response = await self.execute_command(
            'HELO', hostname, timeout=timeout)
        self.last_helo_response = response

        if response.code != SMTPStatus.completed:
            raise SMTPHeloError(response.code, response.message)

        return response

    async def help(
            self, timeout: OptionalDefaultNumber = _default) -> str:
        """
        Send the SMTP HELP command, which responds with help text.

        Raises ``SMTPResponseException`` on an unexpected server response code.
        """
        response = await self.execute_command('HELP', timeout=timeout)
        success_codes = (
            SMTPStatus.system_status_ok, SMTPStatus.help_message,
            SMTPStatus.completed,
        )
        if response.code not in success_codes:
            raise SMTPResponseException(response.code, response.message)

        return response.message

    async def rset(
            self, timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send an SMTP RSET command, which resets the server's envelope
        (the envelope contains the sender, recipient, and mail data).

        Raises ``SMTPResponseException`` on an unexpected server response code.
        """
        response = await self.execute_command('RSET', timeout=timeout)
        if response.code != SMTPStatus.completed:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def noop(
            self, timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send an SMTP NOOP command, which does nothing.

        Raises ``SMTPResponseException`` on an unexpected server response code.
        """
        response = await self.execute_command('NOOP', timeout=timeout)
        if response.code != SMTPStatus.completed:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def vrfy(
            self, address: str,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send an SMTP VRFY command, which tests an address for validity.
        Not many servers support this command.

        Raises ``SMTPResponseException`` on an unexpected server response code.
        """
        parsed_address = parse_address(address)

        response = await self.execute_command(
            'VRFY', parsed_address, timeout=timeout)

        success_codes = (
            SMTPStatus.completed, SMTPStatus.will_forward,
            SMTPStatus.cannot_vrfy,
        )

        if response.code not in success_codes:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def expn(
            self, address: str,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send an SMTP EXPN command, which expands a mailing list.
        Not many servers support this command.

        Raises ``SMTPResponseException`` on an unexpected server response code.
        """
        parsed_address = parse_address(address)

        response = await self.execute_command(
            'EXPN', parsed_address, timeout=timeout)

        if response.code != SMTPStatus.completed:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def quit(
            self, timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send the SMTP QUIT command, which closes the connection.
        Also closes the connection from our side after a response is recieved.

        Raises ``SMTPResponseException`` on an unexpected server response code.
        """
        response = await self.execute_command('QUIT', timeout=timeout)
        if response.code != SMTPStatus.closing:
            raise SMTPResponseException(response.code, response.message)

        self.close()

        return response

    async def mail(
            self, sender: str, options: Iterable[str] = None,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send an SMTP MAIL command, which specifies the message sender and
        begins a new mail transfer session ("envelope").

        Raises ``SMTPSenderRefused`` on an unexpected server response code.
        """
        if options is None:
            options = []
        from_string = 'FROM:{}'.format(quote_address(sender))

        response = await self.execute_command(
            'MAIL', from_string, *options, timeout=timeout)

        if response.code != SMTPStatus.completed:
            raise SMTPSenderRefused(response.code, response.message, sender)

        return response

    async def rcpt(
            self, recipient: str,
            options: Iterable[str] = None,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send an SMTP RCPT command, which specifies a single recipient for
        the message. This command is sent once per recipient and must be
        preceeded by 'MAIL'.

        Raises ``SMTPRecipientRefused`` on an unexpected server response code.
        """
        if options is None:
            options = []
        to = 'TO:{}'.format(quote_address(recipient))

        response = await self.execute_command(
            'RCPT', to, *options, timeout=timeout)

        success_codes = (SMTPStatus.completed, SMTPStatus.will_forward)
        if response.code not in success_codes:
            raise SMTPRecipientRefused(
                response.code, response.message, recipient)

        return response

    async def data(
            self, message: Union[str, bytes],
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send an SMTP DATA command, followed by the message given.
        This method transfers the actual email content to the server.

        Raises ``SMTPDataError`` on an unexpected server response code.
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore

        start_response = await self.execute_command('DATA', timeout=timeout)

        if start_response.code != SMTPStatus.start_input:
            raise SMTPDataError(start_response.code, start_response.message)

        if isinstance(message, str):
            message = message.encode('utf-8')

        await self.protocol.write_message_data(  # type: ignore
            message, timeout=timeout)

        response = await self.protocol.read_response(  # type: ignore
            timeout=timeout)
        if response.code != SMTPStatus.completed:
            raise SMTPDataError(response.code, response.message)

        return response

    # ESMTP commands #

    def supports_extension(self, extension: str) -> bool:
        """
        Tests if the server supports the ESMTP service extension given.
        """
        return extension.lower() in self.esmtp_extensions

    def _reset_server_state(self):
        """
        Clear stored information about the server.
        """
        self.last_helo_response = None
        self._last_ehlo_response = None
        self.esmtp_extensions = {}
        self.supports_esmtp = False
        self.server_auth_methods = []

    async def _ehlo_or_helo_if_needed(self) -> None:
        """
        Call self.ehlo() and/or self.helo() if needed.

        If there has been no previous EHLO or HELO command this session, this
        method tries ESMTP EHLO first.
        """
        self._raise_error_if_disconnected()

        if self.is_ehlo_or_helo_needed:
            try:
                await self.ehlo()
            except SMTPHeloError:
                await self.helo()

    async def ehlo(
            self, hostname: str = None,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send the SMTP EHLO command.
        Hostname to send for this command defaults to the FQDN of the local
        host.
        """
        if hostname is None:
            hostname = self.source_address

        response = await self.execute_command(
            'EHLO', hostname, timeout=timeout)
        self.last_ehlo_response = response

        if response.code != SMTPStatus.completed:
            raise SMTPHeloError(response.code, response.message)

        return response

    async def auth(
            self, auth_method: AuthFunctionType, username: str, password: str,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send an SMTP AUTH command. The actual command sent depends on the
        ``auth_method`` function provided.
        """
        request_command, auth_callback = auth_method(username, password)
        response = await self.execute_command(
            'AUTH', request_command, timeout=timeout)

        if response.code == SMTPStatus.auth_continue and auth_callback:
            next_command = auth_callback(response.code, response.message)
            response = await self.execute_command(
                next_command, timeout=timeout)

        return response

    async def starttls(
            self, server_hostname: str = None, validate_certs: bool = None,
            client_cert: OptionalDefaultStr = _default,
            client_key: OptionalDefaultStr = _default,
            tls_context: OptionalDefaultSSLContext = _default,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Puts the connection to the SMTP server into TLS mode.

        If there has been no previous EHLO or HELO command this session, this
        method tries ESMTP EHLO first.

        If the server supports TLS, this will encrypt the rest of the SMTP
        session. If you provide the keyfile and certfile parameters,
        the identity of the SMTP server and client can be checked (if
        validate_certs is True). You can also provide a custom SSLContext
        object. If no certs or SSLContext is given, and TLS config was
        provided when initializing the class, STARTTLS will use to that,
        otherwise it will use the Python defaults.
        """
        if validate_certs is not None:
            self.validate_certs = validate_certs
        if timeout is _default:
            timeout = self.timeout
        if client_cert is not _default:
            self.client_cert = client_cert  # type: ignore
        if client_key is not _default:
            self.client_key = client_key  # type: ignore
        if tls_context is not _default:
            self.tls_context = tls_context  # type: ignore

        if self.tls_context and self.client_cert:
            raise ValueError(
                'Either a TLS context or a certificate/key must be provided')

        if server_hostname is None:
            server_hostname = self.hostname

        tls_context = self._get_tls_context()

        await self._ehlo_or_helo_if_needed()

        if not self.supports_extension('starttls'):
            raise SMTPException(
                'SMTP STARTTLS extension not supported by server.')

        response, tls_protocol = await self.protocol.starttls(  # type: ignore
            tls_context, server_hostname=server_hostname, timeout=timeout)
        self.transport = tls_protocol._app_transport

        if response.code == SMTPStatus.ready:
            # RFC 3207 part 4.2:
            # The client MUST discard any knowledge obtained from
            # the server, such as the list of SMTP service extensions,
            # which was not obtained from the TLS negotiation itself.
            self._reset_server_state()

        return response

    async def login(
            self, username: str, password: str,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Tries to login with supported auth methods.

        Some servers advertise authentication methods they don't really
        support, so if authentication fails, we continue until we've tried
        all methods.
        """
        await self._ehlo_or_helo_if_needed()

        if not self.supports_extension('auth'):
            raise SMTPException('SMTP AUTH extension not supported by server.')

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
        """
        Send the recipients given to the server. Used as part of ``sendmail``.
        """
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
            sender, recipients, flat_message, mail_options=mail_options,
            rcpt_options=rcpt_options, timeout=timeout)

        return result

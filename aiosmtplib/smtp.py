"""
SMTP client class for use with asyncio.

Author: Cole Maclean <hi@cole.io>
Based on smtplib (from the Python 3 standard library) by:
The Dragon De Monsyne <dragondm@integral.org>
"""
import io
import copy
import socket
import asyncio
import email.utils
import email.generator
from ssl import SSLContext
from enum import Enum
from typing import Any, Union, Iterable, Dict, List, Tuple, Optional  # NOQA

from aiosmtplib import status
from aiosmtplib.auth import AUTH_METHODS, AuthFunctionType
from aiosmtplib.streams import SMTPProtocol, SMTPStreamReader, SMTPStreamWriter
from aiosmtplib.errors import (
    SMTPException, SMTPConnectError, SMTPHeloError, SMTPDataError,
    SMTPRecipientRefused, SMTPRecipientsRefused, SMTPSenderRefused,
    SMTPServerDisconnected, SMTPResponseException, SMTPAuthenticationError,
)
from aiosmtplib.response import SMTPResponse
from aiosmtplib.textutils import (
    quote_address, extract_sender, extract_recipients, encode_message_string,
    parse_esmtp_extensions,
)
from aiosmtplib.tls import configure_tls_context


MAX_LINE_LENGTH = 8192
SMTP_PORT = 25
SMTP_TLS_PORT = 465


class Default(Enum):
    """
    Used for type hinting compatible kwarg defaults.
    """
    token = 0


_default = Default.token


class SMTP:
    """
    An SMTP/ESMTP client.
    """

    def __init__(
            self, hostname: str = 'localhost', port: int = None,
            source_address: str = None,
            timeout: Union[int, float, None] = socket._GLOBAL_DEFAULT_TIMEOUT,
            loop: asyncio.AbstractEventLoop = None,
            use_tls: bool = False, validate_certs: bool = True,
            client_cert: str = None, client_key: str = None,
            tls_context: SSLContext = None) -> None:
        # Kwarg defaults are provided here, and saved for connect.
        if tls_context and client_cert:
            raise ValueError(
                'Either a TLS context or a certificate/key must be provided')

        self.hostname = hostname
        self.port = port
        self.timeout = timeout
        self.use_tls = use_tls
        self._source_address = source_address
        self._validate_certs = validate_certs
        self._client_cert = client_cert
        self._client_key = client_key
        self._tls_context = tls_context

        self.loop = loop or asyncio.get_event_loop()
        self.reader = None  # type: SMTPStreamReader
        self.writer = None  # type: SMTPStreamWriter
        self.protocol = None  # type: SMTPProtocol
        self.transport = None  # type: asyncio.BaseTransport

        self._reset_server_state()

    async def __aenter__(self) -> 'SMTP':
        if not self.is_connected:
            await self.connect()

        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        try:
            await self.quit()
        except SMTPServerDisconnected:
            await self.close()

    @property
    def supported_auth_methods(self) -> List[Tuple[str, AuthFunctionType]]:
        return [
            auth for auth in AUTH_METHODS
            if auth[0] in self.server_auth_methods
        ]

    @property
    def is_connected(self) -> bool:
        """
        Check connection status.

        Returns bool
        """
        return bool(self.transport and not self.transport.is_closing())

    @property
    def source_address(self) -> str:
        """
        Get the system hostname to be sent to the SMTP server.
        Simply caches the result of socket.getfqdn.
        """
        if self._source_address is None:
            self._source_address = socket.getfqdn()

        return self._source_address

    @property
    def is_ehlo_or_helo_needed(self) -> bool:
        self._raise_error_if_disconnected()
        return not (self._last_ehlo_response or self._last_helo_response)

    async def connect(
            self, hostname: str = None, port: int = None,
            source_address: Union[str, None, Default] = _default,
            timeout: Union[float, int, None, Default] = _default,
            loop: asyncio.AbstractEventLoop = None,
            use_tls: Union[bool, Default] = _default,
            validate_certs: Union[bool, Default] = _default,
            client_cert: Union[str, None, Default] = _default,
            client_key: Union[str, None, Default] = _default,
            tls_context: Union[SSLContext, None, Default] = _default) -> \
            SMTPResponse:
        """
        Open asyncio streams to the server and check response status.
        """
        # TODO: replace isinstance checks with identity checks
        # when mypy will handle that
        if hostname is not None:
            self.hostname = hostname
        if port is not None:
            self.port = port
        if loop is not None:
            self.loop = loop
        if not isinstance(timeout, Default):
            self.timeout = timeout
        if not isinstance(use_tls, Default):
            self.use_tls = use_tls
        if not isinstance(source_address, Default):
            self._source_address = source_address
        if not isinstance(validate_certs, Default):
            self._validate_certs = validate_certs
        if not isinstance(client_cert, Default):
            self._client_cert = client_cert
        if not isinstance(client_key, Default):
            self._client_key = client_key
        if not isinstance(tls_context, Default):
            self._tls_context = tls_context

        if self._tls_context and self._client_cert:
            raise ValueError(
                'Either a TLS context or a certificate/key must be provided')

        if self.port is None:
            if self.use_tls:
                self.port = SMTP_TLS_PORT
            else:
                self.port = SMTP_PORT

        if self.use_tls and self._tls_context:
            tls_context = self._tls_context
        elif self.use_tls:
                tls_context = configure_tls_context(
                    validate_certs=self._validate_certs,
                    client_cert=self._client_cert, client_key=self._client_key)
        else:
            tls_context = None

        return await self._connect(self.hostname, self.port, tls_context)

    async def _connect(
            self, hostname: str, port: int,
            tls_context: Optional[SSLContext]) -> SMTPResponse:
        """
        Make the actual connection.
        """
        self._reset_server_state()

        self.reader = SMTPStreamReader(limit=MAX_LINE_LENGTH, loop=self.loop)
        self.protocol = SMTPProtocol(self.reader, loop=self.loop)

        try:
            transport, _ = await self.loop.create_connection(  # type: ignore
                lambda: self.protocol, host=hostname, port=port,
                ssl=tls_context)
        except (ConnectionRefusedError, OSError) as err:
            raise SMTPConnectError(
                'Error connecting to {host} on port {port}: {err}'.format(
                    host=hostname, port=port, err=err))
        else:
            self.writer = SMTPStreamWriter(
                transport, self.protocol, self.reader, self.loop)
            self.transport = transport

        code, message = await self.reader.read_response()
        if code != status.SMTP_220_READY:
            raise SMTPConnectError(message)

        return SMTPResponse(code, message)

    async def close(self) -> None:
        """
        Closes the connection.
        """
        if self.transport and not self.transport.is_closing():
            self.transport.close()

        self.reader = None
        self.writer = None
        self.protocol = None
        self.transport = None
        self._reset_server_state()

    def _reset_server_state(self) -> None:
        self._last_helo_response = None  # type: SMTPResponse
        self._last_ehlo_response = None  # type: SMTPResponse
        self.esmtp_extensions = {}  # type: Dict[str, str]
        self.supports_esmtp = False
        self.server_auth_methods = []  # type: List[str]

    def _raise_error_if_disconnected(self) -> None:
        """
        See if we're still connected, and if not, raise an error.
        """
        if not self.is_connected:
            # TODO: maybe SMTPConnectError here if we never were connected?
            raise SMTPServerDisconnected('Not connected to SMTP server')

    def supports_extension(self, extension: str) -> bool:
        """
        Check if the server supports the ESMTP service extension given.

        Returns bool
        """
        return extension.lower() in self.esmtp_extensions

    def get_transport_info(self, key) -> Any:
        """
        Get extra info from the transport.
        Supported keys:
            'peername', 'socket', 'sockname', 'compression', 'cipher',
            'peercert', 'sslcontext', 'ssl_object'
        """
        self._raise_error_if_disconnected()
        assert self.transport is not None

        return self.transport.get_extra_info(key)

    async def execute_command(self, *args: str) -> SMTPResponse:
        """
        Send the commands given and return the reply message.

        Returns an SMTPResponse namedtuple.
        """
        self._raise_error_if_disconnected()
        assert self.writer is not None
        assert self.reader is not None

        command = b' '.join([arg.encode('ascii') for arg in args])

        await self.writer.send_command(command)
        code, message = await self.reader.read_response()

        if code == status.SMTP_NO_RESPONSE_CODE:
            raise SMTPResponseException(
                code, 'Malformed SMTP response: {}'.format(message))
        elif code == status.SMTP_421_DOMAIN_UNAVAILABLE:
            # If the server is unavailable, shut down our connection
            await self.close()

        return SMTPResponse(code, message)

    async def helo(self, hostname: str = None) -> SMTPResponse:
        """
        Send the SMTP 'helo' command.
        Hostname to send for this command defaults to the FQDN of the local
        host.

        This method may raise the following exceptions:

         SMTPHeloError            The server didn't reply properly to
                                  the helo greeting.

        Returns a (code, message) tuple with the server response.
        """
        if hostname is None:
            hostname = self.source_address

        response = await self.execute_command('HELO', hostname)
        self._last_helo_response = response

        if response.code != status.SMTP_250_COMPLETED:
            raise SMTPHeloError(response.code, response.message)

        return response

    async def ehlo(self, hostname: str = None) -> SMTPResponse:
        """
        Send the SMTP 'ehlo' command.
        Hostname to send for this command defaults to the FQDN of the local
        host.

        Returns an SMTPResponse namedtuple.
        """
        if hostname is None:
            hostname = self.source_address

        response = await self.execute_command('EHLO', hostname)
        self._last_ehlo_response = response

        if response.code == status.SMTP_250_COMPLETED:
            extensions, auth_methods = parse_esmtp_extensions(response.message)
            self.esmtp_extensions = extensions
            self.server_auth_methods = auth_methods
            self.supports_esmtp = True
        else:
            raise SMTPHeloError(response.code, response.message)

        return response

    async def ehlo_or_helo_if_needed(self) -> None:
        """
        Call self.ehlo() and/or self.helo() if needed.

        If there has been no previous EHLO or HELO command this session, this
        method tries ESMTP EHLO first.

        This method may raise the following exceptions:

         SMTPHeloError            The server didn't reply properly to
                                  the helo greeting.
        """
        if self.is_ehlo_or_helo_needed:
            try:
                await self.ehlo()
            except SMTPHeloError:
                await self.helo()

    async def help(self) -> SMTPResponse:
        """
        SMTP 'help' command.
        Returns help text.
        """
        response = await self.execute_command('HELP')
        if response.code not in status.HELP_SUCCESS_STATUSES:
            raise SMTPResponseException(response.code, response.message)

        return response.message

    async def rset(self) -> SMTPResponse:
        """
        Sends an SMTP 'rset' command (resets session)

        Returns an SMTPResponse namedtuple.
        """
        response = await self.execute_command('RSET')
        if response.code != status.SMTP_250_COMPLETED:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def noop(self) -> SMTPResponse:
        """
        Sends an SMTP 'noop' command (does nothing)

        Returns an SMTPResponse namedtuple.
        """
        response = await self.execute_command('NOOP')
        if response.code != status.SMTP_250_COMPLETED:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def vrfy(self, address: str) -> SMTPResponse:
        """
        Sends an SMTP 'vrfy' command (tests an address for validity)

        Returns an SMTPResponse namedtuple.
        """
        parsed_address = email.utils.parseaddr(address)[1] or address
        response = await self.execute_command('VRFY', parsed_address)
        if response.code not in status.VRFY_SUCCESS_STATUSES:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def expn(self, address: str) -> SMTPResponse:
        """
        Sends an SMTP 'expn' command (expands a mailing list)

        Returns an SMTPResponse namedtuple.
        """
        parsed_address = email.utils.parseaddr(address)[1] or address
        response = await self.execute_command('EXPN', parsed_address)

        if response.code != status.SMTP_250_COMPLETED:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def quit(self) -> SMTPResponse:
        """
        Sends the SMTP 'quit' command, and closes the connection.

        Returns an SMTPResponse namedtuple.
        """
        response = await self.execute_command('QUIT')
        if response.code != status.SMTP_221_CLOSING:
            raise SMTPResponseException(response.code, response.message)

        await self.close()
        return response

    async def mail(
            self, sender: str, options: Iterable[str] = None) -> SMTPResponse:
        """
        Sends the SMTP 'mail' command (begins mail transfer session)

        Returns an SMTPResponse namedtuple.

        Raises SMTPSenderRefused if the response is not 250.
        """
        if options is None:
            options = []
        from_string = 'FROM:{}'.format(quote_address(sender))

        response = await self.execute_command('MAIL', from_string, *options)

        if response.code != status.SMTP_250_COMPLETED:
            try:
                await self.rset()
            except SMTPServerDisconnected:
                # If we're disconnected on the reset, don't raise that yet
                # as it's confusing
                pass
            raise SMTPSenderRefused(response.code, response.message, sender)

        return response

    async def rcpt(
            self, recipient: str,
            options: Iterable[str] = None) -> SMTPResponse:
        """
        Sends the SMTP 'rcpt' command (specifies a recipient for the message)

        Returns an SMTPResponse namedtuple.
        """
        if options is None:
            options = []
        to = 'TO:{}'.format(quote_address(recipient))

        response = await self.execute_command('RCPT', to, *options)

        if response.code not in status.RCPT_SUCCESS_STATUSES:
            raise SMTPRecipientRefused(
                response.code, response.message, recipient)

        return response

    async def data(self, message) -> SMTPResponse:
        """
        Sends the SMTP 'data' command (sends message data to server)

        Raises SMTPDataError if there is an unexpected reply to the
        DATA command.

        Returns an SMTPResponse tuple (the last one, after all data is sent.)
        """
        start_response = await self.execute_command('DATA')

        if start_response.code != status.SMTP_354_START_INPUT:
            raise SMTPDataError(start_response.code, start_response.message)

        assert self.writer is not None
        assert self.reader is not None

        encoded_message = encode_message_string(message)
        self.writer.write(encoded_message)
        await self.writer.drain()  # type: ignore

        code, message = await self.reader.read_response()
        if code != status.SMTP_250_COMPLETED:
            raise SMTPDataError(code, message)

        return SMTPResponse(code, message)

    async def sendmail(
            self, sender: str, recipients: Union[str, List[str]],
            message: str, mail_options: List[str] = None,
            rcpt_options: List[str] = None):
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

        """
        if isinstance(recipients, str):
            recipients = [recipients]
        if mail_options is None:
            mail_options = []
        if rcpt_options is None:
            rcpt_options = []

        await self.ehlo_or_helo_if_needed()

        if self.supports_esmtp and self.supports_extension('size'):
            size_option = 'size={}'.format(len(message))
            mail_options.append(size_option)

        await self.mail(sender, options=mail_options)

        recipient_errors = []
        for address in recipients:
            try:
                await self.rcpt(address, options=rcpt_options)
            except SMTPRecipientRefused as exc:
                recipient_errors.append(exc)

        if len(recipient_errors) == len(recipients):
            raise SMTPRecipientsRefused(recipient_errors)

        response = await self.data(message)

        formatted_errors = {
            err.recipient: (err.code, err.message)
            for err in recipient_errors
        }

        return formatted_errors, response.message

    async def send_message(
            self, message: email.message.Message, sender: str = None,
            recipients: Union[str, List[str]] = None,
            mail_options: List[str] = None, rcpt_options: List[str] = None):
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
        resent_dates = message.get_all('Resent-Date')
        if resent_dates and len(resent_dates) > 1:
            raise ValueError(
                "Message has more than one 'Resent-' header block")

        if sender is None:
            sender = extract_sender(message, resent_dates=resent_dates)

        if recipients is None:
            recipients = extract_recipients(message, resent_dates=resent_dates)

        # Make a local copy so we can delete the bcc headers.
        message_copy = copy.copy(message)
        del message_copy['Bcc']
        del message_copy['Resent-Bcc']

        messageio = io.StringIO()
        generator = email.generator.Generator(messageio)
        generator.flatten(message_copy, linesep='\r\n')
        flat_message = messageio.getvalue()

        result = await self.sendmail(
            sender, recipients, flat_message, mail_options=mail_options,
            rcpt_options=rcpt_options)

        return result

    # ESMTP extensions #
    async def _auth(
            self, auth_method: AuthFunctionType, username: str,
            password: str) -> SMTPResponse:
        """
        Try a single auth method. Used as part of login.

        Returns an SMTPResponse tuple.
        """
        request_command, auth_callback = auth_method(username, password)
        response = await self.execute_command('AUTH', request_command)

        if response.code == status.SMTP_334_AUTH_CONTINUE and auth_callback:
            next_command = auth_callback(response.code, response.message)
            response = await self.execute_command(next_command)

        return response

    async def login(self, username: str, password: str) -> SMTPResponse:
        """
        SMTP Login command. Tries all supported auth methods in order.
        """
        await self.ehlo_or_helo_if_needed()

        if not self.supports_extension('auth'):
            raise SMTPException('SMTP AUTH extension not supported by server.')

        # Some servers advertise authentication methods they don't really
        # support, so if authentication fails, we continue until we've tried
        # all methods.
        response = None
        for auth_name, auth_method in self.supported_auth_methods:
            response = await self._auth(auth_method, username, password)

            if response.code == status.SMTP_235_AUTH_SUCCESSFUL:
                break
        else:
            if response is None:
                raise SMTPException('No suitable authentication method found.')
            else:
                raise SMTPAuthenticationError(response.code, response.message)

        return response

    async def starttls(
            self, server_hostname: str = None,
            validate_certs: Union[bool, Default] = _default,
            client_cert: Union[str, None, Default] = _default,
            client_key: Union[str, None, Default] = _default,
            tls_context: Union[SSLContext, None, Default] = _default) -> \
            SMTPResponse:
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

        This method may raise the following exceptions:

         SMTPHeloError            The server didn't reply properly to
                                  the helo greeting.
         ValueError               An unsupported combination of args was
                                  provided.
        """
        if not isinstance(validate_certs, Default):
            self._validate_certs = validate_certs
        if not isinstance(client_cert, Default):
            self._client_cert = client_cert
        if not isinstance(client_key, Default):
            self._client_key = client_key
        if not isinstance(tls_context, Default):
            self._tls_context = tls_context

        if self._tls_context and self._client_cert:
            raise ValueError(
                'Either a TLS context or a certificate/key must be provided')

        if server_hostname is None:
            server_hostname = self.hostname

        if self._tls_context:
            tls_context = self._tls_context
        else:
            tls_context = configure_tls_context(
                validate_certs=self._validate_certs,
                client_cert=self._client_cert, client_key=self._client_key)

        await self.ehlo_or_helo_if_needed()

        if not self.supports_extension('starttls'):
            raise SMTPException(
                'SMTP STARTTLS extension not supported by server.')

        response = await self.execute_command('STARTTLS')

        assert self.writer is not None

        if response.code == status.SMTP_220_READY:
            self.protocol, self.transport = await self.writer.start_tls(
                tls_context, server_hostname=server_hostname)

            # RFC 3207 part 4.2:
            # The client MUST discard any knowledge obtained from
            # the server, such as the list of SMTP service extensions,
            # which was not obtained from the TLS negotiation itself.
            self._reset_server_state()

        return response

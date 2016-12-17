"""
aiosmtplib.esmtp
===================

ESMTP extension handling.
"""
import re
from typing import Dict, List, Tuple

from aiosmtplib.auth import AUTH_METHODS
from aiosmtplib.commands import SMTPCommands
from aiosmtplib.errors import SMTPException, SMTPHeloError
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus
from aiosmtplib.typing import (
    AuthFunctionType, OptionalDefaultNumber, OptionalDefaultSSLContext,
    OptionalDefaultStr, _default,
)

__all__ = ('ESMTP', 'parse_esmtp_extensions',)

OLDSTYLE_AUTH_REGEX = re.compile(r'auth=(?P<auth>.*)', flags=re.I)
EXTENSIONS_REGEX = re.compile(r'(?P<ext>[A-Za-z0-9][A-Za-z0-9\-]*) ?')


class ESMTP(SMTPCommands):
    """
    This class implements support for ESMTP (the EHLO command, and the AUTH
    and STARTTLS extensions). It also keeps track of server state required
    for ESMTP extensions.
    """
    def __init__(self, *args, **kwargs):
        self._last_ehlo_response = None  # type: SMTPResponse
        self.esmtp_extensions = {}  # type: Dict[str, str]
        self.supports_esmtp = False  # type: bool
        self.server_auth_methods = []  # type: List[str]
        super().__init__(*args, **kwargs)

    @property
    def last_ehlo_response(self) -> SMTPResponse:
        return self._last_ehlo_response

    @last_ehlo_response.setter
    def last_ehlo_response(self, response: SMTPResponse) -> None:
        extensions, auth_methods = parse_esmtp_extensions(response.message)
        self._last_ehlo_response = response
        self.esmtp_extensions = extensions
        self.server_auth_methods = auth_methods
        self.supports_esmtp = True

    @property
    def is_ehlo_or_helo_needed(self) -> bool:
        return (
            self.last_ehlo_response is None and
            self.last_helo_response is None)

    @property
    def supported_auth_methods(self) -> List[Tuple[str, AuthFunctionType]]:
        return [
            auth for auth in AUTH_METHODS
            if auth[0] in self.server_auth_methods
        ]

    def supports_extension(self, extension: str) -> bool:
        """
        Check if the server supports the ESMTP service extension given.

        Returns bool
        """
        return extension.lower() in self.esmtp_extensions

    def _reset_server_state(self):
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
        if self.is_ehlo_or_helo_needed:
            try:
                await self.ehlo()
            except SMTPHeloError:
                await self.helo()

    async def ehlo(
            self, hostname: str = None,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send the SMTP 'ehlo' command.
        Hostname to send for this command defaults to the FQDN of the local
        host.

        Returns an SMTPResponse namedtuple.
        """
        if hostname is None:
            hostname = self.source_address
        if timeout is _default:
            timeout = self.timeout  # type: ignore

        self._raise_error_if_disconnected()

        response = await self.protocol.execute_command(  # type: ignore
            'EHLO', hostname, timeout=timeout)
        self.last_ehlo_response = response

        if response.code != SMTPStatus.completed:
            raise SMTPHeloError(response.code, response.message)

        return response

    async def auth(
            self, auth_method: AuthFunctionType, username: str, password: str,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Try a single auth method. Used as part of login.
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore

        request_command, auth_callback = auth_method(username, password)
        response = await self.protocol.execute_command(  # type: ignore
            'AUTH', request_command, timeout=timeout)

        if response.code == SMTPStatus.auth_continue and auth_callback:
            next_command = auth_callback(response.code, response.message)
            response = await self.protocol.execute_command(  # type: ignore
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

        This method may raise the following exceptions:

         SMTPHeloError            The server didn't reply properly to
                                  the helo greeting.
         ValueError               An unsupported combination of args was
                                  provided.
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

        self._raise_error_if_disconnected()
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


def parse_esmtp_extensions(message: str) -> Tuple[Dict[str, str], List[str]]:
    """
    Parse an ESMTP response from the server.

    It might look something like:
         220 size.does.matter.af.MIL (More ESMTP than Crappysoft!)
         EHLO heaven.af.mil
         250-size.does.matter.af.MIL offers FIFTEEN extensions:
         250-8BITMIME
         250-PIPELINING
         250-DSN
         250-ENHANCEDSTATUSCODES
         250-EXPN
         250-HELP
         250-SAML
         250-SEND
         250-SOML
         250-TURN
         250-XADR
         250-XSTA
         250-ETRN
         250-XGEN
         250 SIZE 51200000
    """
    esmtp_extensions = {}  # type: Dict[str, str]
    auth_types = []  # type: List[str]

    response_lines = message.split('\n')

    # ignore the first line
    for line in response_lines[1:]:
        # To be able to communicate with as many SMTP servers as possible,
        # we have to take the old-style auth advertisement into account,
        # because:
        # 1) Else our SMTP feature parser gets confused.
        # 2) There are some servers that only advertise the auth methods we
        #    support using the old style.
        auth_match = OLDSTYLE_AUTH_REGEX.match(line)
        if auth_match:
            auth_type = auth_match.group('auth')[0]
            if auth_type not in auth_types:
                auth_types.append(auth_type.lower().strip())

        # RFC 1869 requires a space between ehlo keyword and parameters.
        # It's actually stricter, in that only spaces are allowed between
        # parameters, but were not going to check for that here.  Note
        # that the space isn't present if there are no parameters.
        extensions = EXTENSIONS_REGEX.match(line)
        if extensions:
            extension = extensions.group('ext').lower()
            params = extensions.string[extensions.end('ext'):].strip()
            esmtp_extensions[extension] = params

            if extension == 'auth':
                auth_types.extend(
                    [param.strip().lower() for param in params.split()])

    return esmtp_extensions, auth_types

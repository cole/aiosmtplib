"""
Low level ESMTP command API.
"""
import re
import ssl
from typing import Dict, Iterable, List, Optional, Tuple, Union

from .connection import SMTPConnection
from .default import Default, _default
from .email import parse_address, quote_address
from .errors import (
    SMTPException,
    SMTPHeloError,
    SMTPNotSupported,
    SMTPRecipientRefused,
    SMTPResponseException,
    SMTPSenderRefused,
    SMTPServerDisconnected,
)
from .response import SMTPResponse
from .status import SMTPStatus


__all__ = ("ESMTP",)


OLDSTYLE_AUTH_REGEX = re.compile(r"auth=(?P<auth>.*)", flags=re.I)
EXTENSIONS_REGEX = re.compile(r"(?P<ext>[A-Za-z0-9][A-Za-z0-9\-]*) ?")


class ESMTP(SMTPConnection):
    """
    Handles individual SMTP and ESMTP commands.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.last_helo_response = None  # type: Optional[SMTPResponse]
        self._last_ehlo_response = None  # type: Optional[SMTPResponse]
        self.esmtp_extensions = {}  # type: Dict[str, str]
        self.supports_esmtp = False
        self.server_auth_methods = []  # type: List[str]

    @property
    def last_ehlo_response(self) -> Union[SMTPResponse, None]:
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
        Check if we've already received a response to an EHLO or HELO command.
        """
        return self.last_ehlo_response is None and self.last_helo_response is None

    def close(self) -> None:
        """
        Makes sure we reset ESMTP state on close.
        """
        super().close()
        self._reset_server_state()

    # Base SMTP commands #

    async def helo(
        self, hostname: str = None, timeout: Optional[Union[float, Default]] = _default
    ) -> SMTPResponse:
        """
        Send the SMTP HELO command.
        Hostname to send for this command defaults to the FQDN of the local
        host.

        :raises SMTPHeloError: on unexpected server response code
        """
        if hostname is None:
            hostname = self.source_address
        response = await self.execute_command(
            b"HELO", hostname.encode("ascii"), timeout=timeout
        )
        self.last_helo_response = response

        if response.code != SMTPStatus.completed:
            raise SMTPHeloError(response.code, response.message)

        return response

    async def help(self, timeout: Optional[Union[float, Default]] = _default) -> str:
        """
        Send the SMTP HELP command, which responds with help text.

        :raises SMTPResponseException: on unexpected server response code
        """
        await self._ehlo_or_helo_if_needed()

        response = await self.execute_command(b"HELP", timeout=timeout)
        if response.code not in (
            SMTPStatus.system_status_ok,
            SMTPStatus.help_message,
            SMTPStatus.completed,
        ):
            raise SMTPResponseException(response.code, response.message)

        return response.message

    async def rset(
        self, timeout: Optional[Union[float, Default]] = _default
    ) -> SMTPResponse:
        """
        Send an SMTP RSET command, which resets the server's envelope
        (the envelope contains the sender, recipient, and mail data).

        :raises SMTPResponseException: on unexpected server response code
        """
        await self._ehlo_or_helo_if_needed()

        response = await self.execute_command(b"RSET", timeout=timeout)
        if response.code != SMTPStatus.completed:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def noop(
        self, timeout: Optional[Union[float, Default]] = _default
    ) -> SMTPResponse:
        """
        Send an SMTP NOOP command, which does nothing.

        :raises SMTPResponseException: on unexpected server response code
        """
        await self._ehlo_or_helo_if_needed()

        response = await self.execute_command(b"NOOP", timeout=timeout)
        if response.code != SMTPStatus.completed:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def vrfy(
        self,
        address: str,
        options: Optional[Iterable[str]] = None,
        timeout: Optional[Union[float, Default]] = _default,
    ) -> SMTPResponse:
        """
        Send an SMTP VRFY command, which tests an address for validity.
        Not many servers support this command.

        :raises SMTPResponseException: on unexpected server response code
        """
        if options is None:
            options = []

        await self._ehlo_or_helo_if_needed()

        parsed_address = parse_address(address)
        if any(option.lower() == "smtputf8" for option in options):
            if not self.supports_extension("smtputf8"):
                raise SMTPNotSupported("SMTPUTF8 is not supported by this server")
            addr_bytes = parsed_address.encode("utf-8")
        else:
            addr_bytes = parsed_address.encode("ascii")
        options_bytes = [option.encode("ascii") for option in options]

        response = await self.execute_command(
            b"VRFY", addr_bytes, *options_bytes, timeout=timeout
        )

        if response.code not in (
            SMTPStatus.completed,
            SMTPStatus.will_forward,
            SMTPStatus.cannot_vrfy,
        ):
            raise SMTPResponseException(response.code, response.message)

        return response

    async def expn(
        self,
        address: str,
        options: Optional[Iterable[str]] = None,
        timeout: Optional[Union[float, Default]] = _default,
    ) -> SMTPResponse:
        """
        Send an SMTP EXPN command, which expands a mailing list.
        Not many servers support this command.

        :raises SMTPResponseException: on unexpected server response code
        """
        if options is None:
            options = []

        await self._ehlo_or_helo_if_needed()

        parsed_address = parse_address(address)
        if any(option.lower() == "smtputf8" for option in options):
            if not self.supports_extension("smtputf8"):
                raise SMTPNotSupported("SMTPUTF8 is not supported by this server")
            addr_bytes = parsed_address.encode("utf-8")
        else:
            addr_bytes = parsed_address.encode("ascii")
        options_bytes = [option.encode("ascii") for option in options]

        response = await self.execute_command(
            b"EXPN", addr_bytes, *options_bytes, timeout=timeout
        )

        if response.code != SMTPStatus.completed:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def quit(
        self, timeout: Optional[Union[float, Default]] = _default
    ) -> SMTPResponse:
        """
        Send the SMTP QUIT command, which closes the connection.
        Also closes the connection from our side after a response is received.

        :raises SMTPResponseException: on unexpected server response code
        """
        # Can't quit without HELO/EHLO
        await self._ehlo_or_helo_if_needed()

        response = await self.execute_command(b"QUIT", timeout=timeout)
        if response.code != SMTPStatus.closing:
            raise SMTPResponseException(response.code, response.message)

        self.close()

        return response

    async def mail(
        self,
        sender: str,
        options: Optional[Iterable[str]] = None,
        encoding: str = "ascii",
        timeout: Optional[Union[float, Default]] = _default,
    ) -> SMTPResponse:
        """
        Send an SMTP MAIL command, which specifies the message sender and
        begins a new mail transfer session ("envelope").

        :raises SMTPSenderRefused: on unexpected server response code
        """
        if options is None:
            options = []

        await self._ehlo_or_helo_if_needed()

        quoted_sender = quote_address(sender)
        addr_bytes = quoted_sender.encode(encoding)
        options_bytes = [option.encode("ascii") for option in options]

        response = await self.execute_command(
            b"MAIL", b"FROM:" + addr_bytes, *options_bytes, timeout=timeout
        )

        if response.code != SMTPStatus.completed:
            raise SMTPSenderRefused(response.code, response.message, sender)

        return response

    async def rcpt(
        self,
        recipient: str,
        options: Optional[Iterable[str]] = None,
        encoding: str = "ascii",
        timeout: Optional[Union[float, Default]] = _default,
    ) -> SMTPResponse:
        """
        Send an SMTP RCPT command, which specifies a single recipient for
        the message. This command is sent once per recipient and must be
        preceded by 'MAIL'.

        :raises SMTPRecipientRefused: on unexpected server response code
        """
        if options is None:
            options = []

        await self._ehlo_or_helo_if_needed()

        quoted_recipient = quote_address(recipient)
        addr_bytes = quoted_recipient.encode(encoding)
        options_bytes = [option.encode("ascii") for option in options]

        response = await self.execute_command(
            b"RCPT", b"TO:" + addr_bytes, *options_bytes, timeout=timeout
        )

        if response.code not in (SMTPStatus.completed, SMTPStatus.will_forward):
            raise SMTPRecipientRefused(response.code, response.message, recipient)

        return response

    async def data(
        self,
        message: Union[str, bytes],
        timeout: Optional[Union[float, Default]] = _default,
    ) -> SMTPResponse:
        """
        Send an SMTP DATA command, followed by the message given.
        This method transfers the actual email content to the server.

        :raises SMTPDataError: on unexpected server response code
        :raises SMTPServerDisconnected: connection lost
        """
        await self._ehlo_or_helo_if_needed()

        # As data accesses protocol directly, some handling is required
        if self.protocol is None:
            raise SMTPServerDisconnected("Connection lost")

        if timeout is _default:
            timeout = self.timeout

        if isinstance(message, str):
            message = message.encode("ascii")

        return await self.protocol.execute_data_command(message, timeout=timeout)

    # ESMTP commands #

    async def ehlo(
        self,
        hostname: Optional[str] = None,
        timeout: Optional[Union[float, Default]] = _default,
    ) -> SMTPResponse:
        """
        Send the SMTP EHLO command.
        Hostname to send for this command defaults to the FQDN of the local
        host.

        :raises SMTPHeloError: on unexpected server response code
        """
        if hostname is None:
            hostname = self.source_address

        response = await self.execute_command(
            b"EHLO", hostname.encode("ascii"), timeout=timeout
        )
        self.last_ehlo_response = response

        if response.code != SMTPStatus.completed:
            raise SMTPHeloError(response.code, response.message)

        return response

    def supports_extension(self, extension: str) -> bool:
        """
        Tests if the server supports the ESMTP service extension given.
        """
        return extension.lower() in self.esmtp_extensions

    async def _ehlo_or_helo_if_needed(self) -> None:
        """
        Call self.ehlo() and/or self.helo() if needed.

        If there has been no previous EHLO or HELO command this session, this
        method tries ESMTP EHLO first.
        """
        if self.is_ehlo_or_helo_needed:
            try:
                await self.ehlo()
            except SMTPHeloError as exc:
                if self.is_connected:
                    await self.helo()
                else:
                    raise exc

    def _reset_server_state(self) -> None:
        """
        Clear stored information about the server.
        """
        self.last_helo_response = None
        self._last_ehlo_response = None
        self.esmtp_extensions = {}
        self.supports_esmtp = False
        self.server_auth_methods = []

    async def starttls(
        self,
        server_hostname: Optional[str] = None,
        validate_certs: Optional[bool] = None,
        client_cert: Optional[Union[str, Default]] = _default,
        client_key: Optional[Union[str, Default]] = _default,
        cert_bundle: Optional[Union[str, Default]] = _default,
        tls_context: Optional[Union[ssl.SSLContext, Default]] = _default,
        timeout: Optional[Union[float, Default]] = _default,
    ) -> SMTPResponse:
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

        :raises SMTPException: server does not support STARTTLS
        :raises SMTPServerDisconnected: connection lost
        :raises ValueError: invalid options provided
        """
        await self._ehlo_or_helo_if_needed()
        if self.protocol is None:
            raise SMTPServerDisconnected("Server not connected")

        self._update_settings_from_kwargs(
            validate_certs=validate_certs,
            client_cert=client_cert,
            client_key=client_key,
            cert_bundle=cert_bundle,
            tls_context=tls_context,
            timeout=timeout,
        )
        self._validate_config()

        if server_hostname is None:
            server_hostname = self.hostname

        tls_context = self._get_tls_context()

        if not self.supports_extension("starttls"):
            raise SMTPException("SMTP STARTTLS extension not supported by server.")

        response = await self.protocol.start_tls(
            tls_context, server_hostname=server_hostname, timeout=self.timeout
        )
        if self.protocol is None:
            raise SMTPServerDisconnected("Connection lost")
        # Update our transport reference
        self.transport = self.protocol.transport

        # RFC 3207 part 4.2:
        # The client MUST discard any knowledge obtained from the server, such
        # as the list of SMTP service extensions, which was not obtained from
        # the TLS negotiation itself.
        self._reset_server_state()

        return response


def parse_esmtp_extensions(message: str) -> Tuple[Dict[str, str], List[str]]:
    """
    Parse an EHLO response from the server into a dict of {extension: params}
    and a list of auth method names.

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
    esmtp_extensions = {}
    auth_types = []  # type: List[str]

    response_lines = message.split("\n")

    # ignore the first line
    for line in response_lines[1:]:
        # To be able to communicate with as many SMTP servers as possible,
        # we have to take the old-style auth advertisement into account,
        # because:
        # 1) Else our SMTP feature parser gets confused.
        # 2) There are some servers that only advertise the auth methods we
        #    support using the old style.
        auth_match = OLDSTYLE_AUTH_REGEX.match(line)
        if auth_match is not None:
            auth_type = auth_match.group("auth")
            auth_types.append(auth_type.lower().strip())

        # RFC 1869 requires a space between ehlo keyword and parameters.
        # It's actually stricter, in that only spaces are allowed between
        # parameters, but were not going to check for that here.  Note
        # that the space isn't present if there are no parameters.
        extensions = EXTENSIONS_REGEX.match(line)
        if extensions is not None:
            extension = extensions.group("ext").lower()
            params = extensions.string[extensions.end("ext") :].strip()
            esmtp_extensions[extension] = params

            if extension == "auth":
                auth_types.extend([param.strip().lower() for param in params.split()])

    return esmtp_extensions, auth_types

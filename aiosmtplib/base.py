"""
aiosmtplib.base
===============
Support for basic SMTP protocol commands.
"""
from typing import Iterable, Union

from aiosmtplib.connection import SMTPConnection
from aiosmtplib.email import parse_address, quote_address
from aiosmtplib.errors import (
    SMTPDataError, SMTPHeloError, SMTPRecipientRefused, SMTPResponseException,
    SMTPSenderRefused,
)
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus
from aiosmtplib.typing import OptionalDefaultNumber, _default

__all__ = ('BaseSMTP',)


class BaseSMTP(SMTPConnection):
    """
    Basic SMTP protocol commands implementation.
    """

    def __init__(self, *args, **kwargs):
        self.last_helo_response = None  # type: SMTPResponse
        super().__init__(*args, **kwargs)

    async def helo(
            self, hostname: str = None,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Send the SMTP 'helo' command.
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
            'HELO', hostname, timeout=timeout)
        self.last_helo_response = response

        if response.code != SMTPStatus.completed:
            raise SMTPHeloError(response.code, response.message)

        return response

    async def help(
            self, timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        SMTP 'help' command.
        Returns help text.
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore

        self._raise_error_if_disconnected()

        response = await self.protocol.execute_command(    # type: ignore
            'HELP', timeout=timeout)
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
        Sends an SMTP 'rset' command (resets session)

        Returns an SMTPResponse namedtuple.
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore

        self._raise_error_if_disconnected()

        response = await self.protocol.execute_command(    # type: ignore
            'RSET', timeout=timeout)
        if response.code != SMTPStatus.completed:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def noop(
            self, timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Sends an SMTP 'noop' command (does nothing)

        Returns an SMTPResponse namedtuple.
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore

        self._raise_error_if_disconnected()

        response = await self.protocol.execute_command(    # type: ignore
            'NOOP', timeout=timeout)
        if response.code != SMTPStatus.completed:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def vrfy(
            self, address: str,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Sends an SMTP 'vrfy' command (tests an address for validity)

        Returns an SMTPResponse namedtuple.
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore
        parsed_address = parse_address(address)

        self._raise_error_if_disconnected()

        response = await self.protocol.execute_command(  # type: ignore
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
        Sends an SMTP 'expn' command (expands a mailing list)

        Returns an SMTPResponse namedtuple.
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore
        parsed_address = parse_address(address)

        self._raise_error_if_disconnected()

        response = await self.protocol.execute_command(  # type: ignore
            'EXPN', parsed_address, timeout=timeout)

        if response.code != SMTPStatus.completed:
            raise SMTPResponseException(response.code, response.message)

        return response

    async def quit(
            self, timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Sends the SMTP 'quit' command, and closes the connection.

        Returns an SMTPResponse namedtuple.
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore

        self._raise_error_if_disconnected()

        response = await self.protocol.execute_command(  # type: ignore
            'QUIT', timeout=timeout)
        if response.code != SMTPStatus.closing:
            raise SMTPResponseException(response.code, response.message)

        self.close()

        return response

    async def mail(
            self, sender: str, options: Iterable[str] = None,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Sends the SMTP 'mail' command (begins mail transfer session)

        Returns an SMTPResponse namedtuple.
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore
        if options is None:
            options = []
        from_string = 'FROM:{}'.format(quote_address(sender))

        self._raise_error_if_disconnected()

        response = await self.protocol.execute_command(  # type: ignore
            'MAIL', from_string, *options, timeout=timeout)

        if response.code != SMTPStatus.completed:
            raise SMTPSenderRefused(response.code, response.message, sender)

        return response

    async def rcpt(
            self, recipient: str,
            options: Iterable[str] = None,
            timeout: OptionalDefaultNumber = _default) -> SMTPResponse:
        """
        Sends the SMTP 'rcpt' command (specifies a recipient for the message)

        Returns an SMTPResponse namedtuple.
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore
        if options is None:
            options = []
        to = 'TO:{}'.format(quote_address(recipient))

        self._raise_error_if_disconnected()

        response = await self.protocol.execute_command(  # type: ignore
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
        Sends the SMTP 'data' command (sends message data to server)

        Raises SMTPDataError if there is an unexpected reply to the
        DATA command.

        Returns an SMTPResponse tuple (the last one, after all data is sent.)
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore

        self._raise_error_if_disconnected()

        start_response = await self.protocol.execute_command(  # type: ignore
            'DATA', timeout=timeout)

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

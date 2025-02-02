"""
Implements handlers required on top of aiosmtpd for testing.
"""

import asyncio
import logging
from email.errors import HeaderParseError
from email.message import EmailMessage, Message
from typing import Any, AnyStr, Optional, Union

from aiosmtpd.handlers import Message as MessageHandler
from aiosmtpd.smtp import MISSING
from aiosmtpd.smtp import SMTP as SMTPD
from aiosmtpd.smtp import Envelope, Session, _Missing

from aiosmtplib import SMTPStatus


log = logging.getLogger("mail.log")


class RecordingHandler(MessageHandler):
    def __init__(
        self,
        messages_list: list[Union[EmailMessage, Message]],
        commands_list: list[tuple[str, tuple[Any, ...]]],
        responses_list: list[str],
    ):
        self.messages = messages_list
        self.commands = commands_list
        self.responses = responses_list
        super().__init__(message_class=EmailMessage)

    def record_command(self, command: str, *args: Any) -> None:
        self.commands.append((command, tuple(args)))

    def record_server_response(self, status: str) -> None:
        self.responses.append(status)

    def handle_message(self, message: Union[EmailMessage, Message]) -> None:
        self.messages.append(message)

    async def handle_EHLO(
        self,
        server: SMTPD,
        session: Session,
        envelope: Envelope,
        hostname: str,
        responses: list[str],
    ) -> list[str]:
        """Advertise auth login support."""
        session.host_name = hostname  # type: ignore
        if server._tls_protocol:
            return ["250-AUTH LOGIN"] + responses
        else:
            return responses


class TestSMTPD(SMTPD):
    transport: Optional[asyncio.BaseTransport]  # type: ignore

    def _getaddr(self, arg: str) -> tuple[Optional[str], Optional[str]]:
        """
        Don't raise an exception on unparsable email address
        """
        address: Optional[str] = None
        rest: Optional[str] = ""
        try:
            address, rest = super()._getaddr(arg)
        except HeaderParseError:
            pass

        return address, rest

    async def _call_handler_hook(self, command: str, *args: Any) -> Any:
        self.event_handler.record_command(command, *args)
        return await super()._call_handler_hook(command, *args)

    async def push(self, status: AnyStr) -> None:
        await super().push(status)
        self.event_handler.record_server_response(status)

    async def smtp_EXPN(self, arg: str) -> None:
        """
        Pass EXPN to handler hook.
        """
        status = await self._call_handler_hook("EXPN")
        await self.push(
            "502 EXPN not implemented" if isinstance(status, _Missing) else status
        )

    async def smtp_HELP(self, arg: str) -> None:
        """
        Override help to pass to handler hook.
        """
        status = await self._call_handler_hook("HELP")
        if status is MISSING:
            await super().smtp_HELP(arg)
        else:
            await self.push(status)

    async def smtp_STARTTLS(self, arg: str) -> None:
        await super().smtp_STARTTLS(arg)
        self.event_handler.record_command("STARTTLS", arg)


async def mock_response_delayed_ok(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    await asyncio.sleep(1.0)
    await smtpd.push("250 all done")


async def mock_response_delayed_read(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    await smtpd.push("220-hi")
    await asyncio.sleep(1.0)


async def mock_response_done(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    if args and args[0]:
        smtpd.session.host_name = args[0]
    await smtpd.push("250 done")


async def mock_response_done_then_close(
    smtpd: SMTPD, *args: Any, **kwargs: Any
) -> None:
    if args and args[0]:
        smtpd.session.host_name = args[0]
    await smtpd.push("250 done")
    await smtpd.push("221 bye now")
    smtpd.transport.close()


async def mock_response_error_disconnect(
    smtpd: SMTPD, *args: Any, **kwargs: Any
) -> None:
    await smtpd.push("501 error")
    smtpd.transport.close()


async def mock_response_bad_data(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    smtpd._writer.write(b"250 \xff\xff\xff\xff\r\n")
    await smtpd._writer.drain()


async def mock_response_gibberish(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    smtpd._writer.write("wefpPSwrsfa2sdfsdf")
    await smtpd._writer.drain()


async def mock_response_expn(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    await smtpd.push(
        """250-Joseph Blow <jblow@example.com>
250 Alice Smith <asmith@example.com>"""
    )


async def mock_response_ehlo_minimal(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    if args and args[0]:
        smtpd.session.host_name = args[0]

    await smtpd.push("250 HELP")


async def mock_response_ehlo_full(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    if args and args[0]:
        smtpd.session.host_name = args[0]

    await smtpd.push(
        """250-localhost
250-PIPELINING
250-8BITMIME
250-SIZE 512000
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
250 XGEN"""
    )


async def mock_response_unavailable(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    await smtpd.push("421 retry in 5 minutes")
    smtpd.transport.close()


async def mock_response_tls_not_available(
    smtpd: SMTPD, *args: Any, **kwargs: Any
) -> None:
    await smtpd.push("454 please login")


async def mock_response_tls_ready_disconnect(
    smtpd: SMTPD, *args: Any, **kwargs: Any
) -> None:
    await smtpd.push("220 go for it")
    smtpd.transport.close()


async def mock_response_start_data_disconnect(
    smtpd: SMTPD, *args: Any, **kwargs: Any
) -> None:
    await smtpd.push("354 ok")
    smtpd.transport.close()


async def mock_response_disconnect(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    smtpd.transport.close()


async def mock_response_eof(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    smtpd.transport.write_eof()


async def mock_response_mailbox_unavailable(
    smtpd: SMTPD, *args: Any, **kwargs: Any
) -> None:
    await smtpd.push(f"{SMTPStatus.mailbox_unavailable} error")


async def mock_response_unrecognized_command(
    smtpd: SMTPD, *args: Any, **kwargs: Any
) -> None:
    await smtpd.push(f"{SMTPStatus.unrecognized_command} error")


async def mock_response_bad_command_sequence(
    smtpd: SMTPD, *args: Any, **kwargs: Any
) -> None:
    await smtpd.push(f"{SMTPStatus.bad_command_sequence} error")


async def mock_response_syntax_error(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
    await smtpd.push(f"{SMTPStatus.syntax_error} error")


async def mock_response_syntax_error_and_cleanup(
    smtpd: SMTPD, *args: Any, **kwargs: Any
) -> None:
    await smtpd.push(f"{SMTPStatus.syntax_error} error")

    if smtpd._handler_coroutine:
        smtpd._handler_coroutine.cancel()
    if smtpd.transport:
        smtpd.transport.close()

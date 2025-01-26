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

"""
send coroutine testing.
"""
import email
from typing import List, Tuple

import pytest

from aiosmtplib import send


pytestmark = pytest.mark.asyncio()


async def test_send(
    hostname: str,
    smtpd_server_port: int,
    message: email.message.Message,
    received_messages: List[email.message.EmailMessage],
) -> None:
    errors, response = await send(message, hostname=hostname, port=smtpd_server_port)

    assert not errors
    assert len(received_messages) == 1


async def test_send_with_str(
    hostname: str,
    smtpd_server_port: int,
    recipient_str: str,
    sender_str: str,
    message_str: str,
    received_messages: List[email.message.EmailMessage],
) -> None:
    errors, response = await send(
        message_str,
        hostname=hostname,
        port=smtpd_server_port,
        sender=sender_str,
        recipients=[recipient_str],
    )

    assert not errors
    assert len(received_messages) == 1


async def test_send_with_bytes(
    hostname: str,
    smtpd_server_port: int,
    recipient_str: str,
    sender_str: str,
    message_str: str,
    received_messages: List[email.message.EmailMessage],
) -> None:
    errors, response = await send(
        bytes(message_str, "ascii"),
        hostname=hostname,
        port=smtpd_server_port,
        sender=sender_str,
        recipients=[recipient_str],
    )

    assert not errors
    assert len(received_messages) == 1


async def test_send_without_sender(
    hostname: str,
    smtpd_server_port: int,
    recipient_str: str,
    message_str: str,
    received_messages: List[email.message.EmailMessage],
) -> None:
    with pytest.raises(ValueError):
        errors, response = await send(  # type: ignore
            message_str,
            hostname=hostname,
            port=smtpd_server_port,
            sender=None,
            recipients=[recipient_str],
        )


async def test_send_without_recipients(
    hostname: str,
    smtpd_server_port: int,
    sender_str: str,
    message_str: str,
    received_messages: List[email.message.EmailMessage],
) -> None:
    with pytest.raises(ValueError):
        errors, response = await send(
            message_str,
            hostname=hostname,
            port=smtpd_server_port,
            sender=sender_str,
            recipients=[],
        )


async def test_send_with_start_tls(
    hostname: str,
    smtpd_server_port: int,
    message: email.message.Message,
    received_messages: List[email.message.EmailMessage],
    received_commands: List[Tuple[str, ...]],
) -> None:
    errors, response = await send(
        message,
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=True,
        validate_certs=False,
    )

    assert not errors
    assert "STARTTLS" in [command[0] for command in received_commands]
    assert len(received_messages) == 1


async def test_send_with_login(
    hostname: str,
    smtpd_server_port: int,
    message: email.message.Message,
    received_messages: List[email.message.EmailMessage],
    received_commands: List[Tuple[str, ...]],
    auth_username: str,
    auth_password: str,
) -> None:
    errors, response = await send(
        message,
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=True,
        validate_certs=False,
        username=auth_username,
        password=auth_password,
    )

    assert not errors
    assert "AUTH" in [command[0] for command in received_commands]
    assert len(received_messages) == 1

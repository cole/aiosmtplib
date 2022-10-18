"""
send coroutine testing.
"""
import asyncio
import email
import pathlib
import socket
import ssl
from typing import Any, List, Tuple, Union

import pytest

from aiosmtplib import send


pytestmark = pytest.mark.asyncio()


async def test_send(
    hostname: str,
    smtpd_server_port: int,
    message: email.message.Message,
    received_messages: List[email.message.EmailMessage],
    client_tls_context: ssl.SSLContext,
) -> None:
    errors, response = await send(
        message,
        hostname=hostname,
        port=smtpd_server_port,
        tls_context=client_tls_context,
    )

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
        start_tls=False,
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
        start_tls=False,
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
        errors, response = await send(
            message_str,
            hostname=hostname,
            port=smtpd_server_port,
            sender=None,
            recipients=[recipient_str],
            start_tls=False,
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
            start_tls=False,
        )


async def test_send_with_start_tls(
    hostname: str,
    smtpd_server_port: int,
    client_tls_context: ssl.SSLContext,
    message: email.message.Message,
    received_messages: List[email.message.EmailMessage],
    received_commands: List[Tuple[str, Tuple[Any, ...]]],
) -> None:
    errors, response = await send(
        message,
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=True,
        tls_context=client_tls_context,
    )

    assert not errors
    assert "STARTTLS" in [command[0] for command in received_commands]
    assert len(received_messages) == 1


async def test_send_with_login(
    hostname: str,
    smtpd_server_port: int,
    message: email.message.Message,
    received_messages: List[email.message.EmailMessage],
    received_commands: List[Tuple[str, Tuple[Any, ...]]],
    auth_username: str,
    auth_password: str,
    client_tls_context: ssl.SSLContext,
) -> None:
    errors, response = await send(
        message,
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=True,
        tls_context=client_tls_context,
        username=auth_username,
        password=auth_password,
    )

    assert not errors
    assert "AUTH" in [command[0] for command in received_commands]
    assert len(received_messages) == 1


async def test_send_via_socket(
    hostname: str,
    smtpd_server_port: int,
    message: email.message.Message,
    received_messages: List[email.message.EmailMessage],
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((hostname, smtpd_server_port))

        errors, response = await send(
            message,
            hostname=None,
            port=None,
            sock=sock,
            start_tls=False,
        )

        assert not errors
        assert len(received_messages) == 1

        assert sock.fileno() > 0, "Socket unexpectedly closed"


async def test_send_via_socket_path(
    smtpd_server_socket_path: asyncio.AbstractServer,
    socket_path: Union[pathlib.Path, str, bytes],
    message: email.message.Message,
    received_messages: List[email.message.EmailMessage],
) -> None:
    errors, response = await send(
        message,
        hostname=None,
        port=None,
        socket_path=socket_path,
        start_tls=False,
    )

    assert not errors
    assert len(received_messages) == 1


async def test_send_with_mail_options(
    hostname: str,
    smtpd_server_port: int,
    recipient_str: str,
    sender_str: str,
    message_str: str,
    received_messages: List[email.message.EmailMessage],
) -> None:
    errors, _ = await send(
        message_str,
        hostname=hostname,
        port=smtpd_server_port,
        sender=sender_str,
        recipients=[recipient_str],
        mail_options=["BODY=8BITMIME"],
        start_tls=False,
    )

    assert not errors
    assert len(received_messages) == 1


async def test_send_with_rcpt_options(
    hostname: str,
    smtpd_server_port: int,
    recipient_str: str,
    sender_str: str,
    message_str: str,
    received_messages: List[email.message.EmailMessage],
) -> None:
    errors, _ = await send(
        message_str,
        hostname=hostname,
        port=smtpd_server_port,
        sender=sender_str,
        recipients=[recipient_str],
        # RCPT params are not supported by the server; just check that the kwarg works
        rcpt_options=[],
        start_tls=False,
    )

    assert not errors
    assert len(received_messages) == 1

"""
send coroutine testing.
"""

import asyncio
import email
import email.message
import pathlib
import socket
import ssl
from typing import Any, Union

import pytest

from aiosmtplib import send


@pytest.mark.parametrize(
    "message", ["message", "compat32_message", "mime_message"], indirect=True
)
async def test_send(
    hostname: str,
    smtpd_server_port: int,
    message: Union[email.message.EmailMessage, email.message.Message],
    received_messages: list[email.message.EmailMessage],
    client_tls_context: ssl.SSLContext,
) -> None:
    errors, _ = await send(
        message,
        hostname=hostname,
        port=smtpd_server_port,
        tls_context=client_tls_context,
    )

    assert not errors
    assert len(received_messages) == 1


@pytest.mark.parametrize("message", ["message_str", "message_bytes"], indirect=True)
async def test_send_with_raw_message(
    hostname: str,
    smtpd_server_port: int,
    recipient_str: str,
    sender_str: str,
    message: Union[str, bytes],
    received_messages: list[email.message.EmailMessage],
) -> None:
    errors, _ = await send(
        message,
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
) -> None:
    with pytest.raises(ValueError):
        await send(
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
) -> None:
    with pytest.raises(ValueError):
        await send(
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
    message: email.message.EmailMessage,
    received_messages: list[email.message.EmailMessage],
    received_commands: list[tuple[str, tuple[Any, ...]]],
) -> None:
    errors, _ = await send(
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
    message: email.message.EmailMessage,
    received_messages: list[email.message.EmailMessage],
    received_commands: list[tuple[str, tuple[Any, ...]]],
    auth_username: str,
    auth_password: str,
    client_tls_context: ssl.SSLContext,
) -> None:
    errors, _ = await send(
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
    message: email.message.EmailMessage,
    received_messages: list[email.message.EmailMessage],
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((hostname, smtpd_server_port))

        errors, _ = await send(
            message,
            hostname=None,
            port=None,
            sock=sock,
            start_tls=False,
        )

        assert not errors
        assert len(received_messages) == 1


@pytest.mark.smtpd_options(tls=True)
async def test_send_via_socket_tls_and_hostname(
    hostname: str,
    client_tls_context: ssl.SSLContext,
    smtpd_server_port: int,
    message: email.message.EmailMessage,
    received_messages: list[email.message.EmailMessage],
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((hostname, smtpd_server_port))

        errors, _ = await send(
            message,
            hostname=hostname,
            port=None,
            sock=sock,
            tls_context=client_tls_context,
            use_tls=True,
        )

        assert not errors
        assert len(received_messages) == 1


@pytest.mark.parametrize(
    "socket_path_type",
    [str, pathlib.Path, bytes],
    ids=["str", "Path", "bytes"],
)
async def test_send_via_socket_path(
    smtpd_server_socket_path: asyncio.AbstractServer,
    socket_path: pathlib.Path,
    socket_path_type: Union[type[str], type[pathlib.Path], type[bytes]],
    message: email.message.EmailMessage,
    received_messages: list[email.message.EmailMessage],
) -> None:
    errors, _ = await send(
        message,
        hostname=None,
        port=None,
        socket_path=socket_path_type(socket_path),
        start_tls=False,
    )

    assert not errors
    assert len(received_messages) == 1


@pytest.mark.smtpd_options(tls=True)
async def test_send_via_socket_path_with_tls(
    smtpd_server_socket_path: asyncio.AbstractServer,
    socket_path: pathlib.Path,
    hostname: str,
    client_tls_context: ssl.SSLContext,
    message: email.message.EmailMessage,
    received_messages: list[email.message.EmailMessage],
) -> None:
    errors, _ = await send(
        message,
        hostname=hostname,
        port=None,
        socket_path=socket_path,
        use_tls=True,
        tls_context=client_tls_context,
    )

    assert not errors
    assert len(received_messages) == 1


async def test_send_with_mail_options(
    hostname: str,
    smtpd_server_port: int,
    recipient_str: str,
    sender_str: str,
    message_str: str,
    received_messages: list[email.message.EmailMessage],
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
    received_messages: list[email.message.EmailMessage],
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

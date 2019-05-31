"""
send_message coroutine testing.
"""
import pytest

import aiosmtplib.api  # For monkeypatching
from aiosmtplib import send_message
from aiosmtplib.connection import SMTP_STARTTLS_PORT

from .mocks import MockSMTP


pytestmark = pytest.mark.asyncio()


async def test_send_message(hostname, port, smtpd_server, message, recieved_messages):
    errors, response = await send_message(message, hostname=hostname, port=port)

    assert not errors
    assert len(recieved_messages) == 1


async def test_send_message_with_str(
    hostname, port, smtpd_server, message, recieved_messages
):
    errors, response = await send_message(
        str(message),
        hostname=hostname,
        port=port,
        sender=message["From"],
        recipients=[message["To"]],
    )

    assert not errors
    assert len(recieved_messages) == 1


async def test_send_message_with_bytes(
    hostname, port, smtpd_server, message, recieved_messages
):
    errors, response = await send_message(
        bytes(message),
        hostname=hostname,
        port=port,
        sender=message["From"],
        recipients=[message["To"]],
    )

    assert not errors
    assert len(recieved_messages) == 1


async def test_send_message_without_sender(
    hostname, port, smtpd_server, message, recieved_messages
):
    with pytest.raises(ValueError):
        errors, response = await send_message(
            bytes(message),
            hostname=hostname,
            port=port,
            sender=None,
            recipients=[message["To"]],
        )


async def test_send_message_without_recipients(
    hostname, port, smtpd_server, message, recieved_messages
):
    with pytest.raises(ValueError):
        errors, response = await send_message(
            bytes(message),
            hostname=hostname,
            port=port,
            sender=message["From"],
            recipients=[],
        )


async def test_send_message_with_start_and_use_tls(
    hostname, port, smtpd_server, message, recieved_messages
):
    with pytest.raises(ValueError):
        errors, response = await send_message(
            message, hostname=hostname, port=port, start_tls=True, use_tls=True
        )


async def test_send_message_with_start_tls(
    hostname, port, smtpd_server, message, recieved_messages, recieved_commands
):
    errors, response = await send_message(
        message, hostname=hostname, port=port, start_tls=True, validate_certs=False
    )

    assert not errors
    assert "STARTTLS" in [command[0] for command in recieved_commands]
    assert len(recieved_messages) == 1


async def test_send_message_with_login(
    hostname, port, smtpd_server, message, recieved_messages, recieved_commands
):
    errors, response = await send_message(  # nosec
        message,
        hostname=hostname,
        port=port,
        start_tls=True,
        validate_certs=False,
        username="test",
        password="test",
    )

    assert not errors
    assert "AUTH" in [command[0] for command in recieved_commands]
    assert len(recieved_messages) == 1


async def test_send_message_start_tls_default_port(monkeypatch, message):
    monkeypatch.setattr(aiosmtplib.api, "SMTP", MockSMTP)

    errors, response = await send_message(message, start_tls=True, validate_certs=False)

    assert MockSMTP.kwargs["port"] == SMTP_STARTTLS_PORT

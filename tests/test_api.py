"""
send coroutine testing.
"""
import pytest

import aiosmtplib.api  # For monkeypatching
from aiosmtplib import send
from aiosmtplib.connection import SMTP_STARTTLS_PORT

from .mocks import MockSMTP


pytestmark = pytest.mark.asyncio()


async def test_send(hostname, port, smtpd_server, message, recieved_messages):
    errors, response = await send(message, hostname=hostname, port=port)

    assert not errors
    assert len(recieved_messages) == 1


async def test_send_with_str(hostname, port, smtpd_server, message, recieved_messages):
    errors, response = await send(
        str(message),
        hostname=hostname,
        port=port,
        sender=message["From"],
        recipients=[message["To"]],
    )

    assert not errors
    assert len(recieved_messages) == 1


async def test_send_with_bytes(
    hostname, port, smtpd_server, message, recieved_messages
):
    errors, response = await send(
        bytes(message),
        hostname=hostname,
        port=port,
        sender=message["From"],
        recipients=[message["To"]],
    )

    assert not errors
    assert len(recieved_messages) == 1


async def test_send_without_sender(
    hostname, port, smtpd_server, message, recieved_messages
):
    with pytest.raises(ValueError):
        errors, response = await send(
            bytes(message),
            hostname=hostname,
            port=port,
            sender=None,
            recipients=[message["To"]],
        )


async def test_send_without_recipients(
    hostname, port, smtpd_server, message, recieved_messages
):
    with pytest.raises(ValueError):
        errors, response = await send(
            bytes(message),
            hostname=hostname,
            port=port,
            sender=message["From"],
            recipients=[],
        )


async def test_send_with_start_and_use_tls(
    hostname, port, smtpd_server, message, recieved_messages
):
    with pytest.raises(ValueError):
        errors, response = await send(
            message, hostname=hostname, port=port, start_tls=True, use_tls=True
        )


async def test_send_with_start_tls(
    hostname, port, smtpd_server, message, recieved_messages, recieved_commands
):
    errors, response = await send(
        message, hostname=hostname, port=port, start_tls=True, validate_certs=False
    )

    assert not errors
    assert "STARTTLS" in [command[0] for command in recieved_commands]
    assert len(recieved_messages) == 1


async def test_send_with_login(
    hostname, port, smtpd_server, message, recieved_messages, recieved_commands
):
    errors, response = await send(  # nosec
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


async def test_send_start_tls_default_port(monkeypatch, message):
    monkeypatch.setattr(aiosmtplib.api, "SMTP", MockSMTP)

    errors, response = await send(message, start_tls=True, validate_certs=False)

    assert MockSMTP.kwargs["port"] == SMTP_STARTTLS_PORT

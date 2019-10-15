"""
send coroutine testing.
"""
import pytest

from aiosmtplib import send


pytestmark = pytest.mark.asyncio()


async def test_send(hostname, smtpd_server_port, message, received_messages):
    errors, response = await send(message, hostname=hostname, port=smtpd_server_port)

    assert not errors
    assert len(received_messages) == 1


async def test_send_with_str(
    hostname,
    smtpd_server_port,
    recipient_str,
    sender_str,
    message_str,
    received_messages,
):
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
    hostname,
    smtpd_server_port,
    recipient_str,
    sender_str,
    message_str,
    received_messages,
):
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
    hostname, smtpd_server_port, recipient_str, message_str, received_messages
):
    with pytest.raises(ValueError):
        errors, response = await send(
            message_str,
            hostname=hostname,
            port=smtpd_server_port,
            sender=None,
            recipients=[recipient_str],
        )


async def test_send_without_recipients(
    hostname, smtpd_server_port, sender_str, message_str, received_messages
):
    with pytest.raises(ValueError):
        errors, response = await send(
            message_str,
            hostname=hostname,
            port=smtpd_server_port,
            sender=sender_str,
            recipients=[],
        )


async def test_send_with_start_tls(
    hostname, smtpd_server_port, message, received_messages, received_commands
):
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
    hostname, smtpd_server_port, message, received_messages, received_commands
):
    errors, response = await send(  # nosec
        message,
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=True,
        validate_certs=False,
        username="test",
        password="test",
    )

    assert not errors
    assert "AUTH" in [command[0] for command in received_commands]
    assert len(received_messages) == 1

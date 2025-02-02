"""
Tests that cover asyncio usage.
"""

import asyncio
import ssl
from collections.abc import Awaitable
from typing import Any

import pytest

from aiosmtplib import SMTP
from aiosmtplib.response import SMTPResponse

from .smtpd import mock_response_expn


RECIPIENTS = [
    "recipient1@example.com",
    "recipient2@example.com",
    "recipient3@example.com",
]


async def test_sendmail_multiple_times_in_sequence(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    sender_str: str,
    message_str: str,
) -> None:
    async with smtp_client:
        for recipient in RECIPIENTS:
            errors, response = await smtp_client.sendmail(
                sender_str, [recipient], message_str
            )

            assert not errors
            assert isinstance(errors, dict)
            assert response != ""


async def test_sendmail_multiple_times_with_gather(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    sender_str: str,
    message_str: str,
) -> None:
    async with smtp_client:
        tasks = [
            smtp_client.sendmail(sender_str, [recipient], message_str)
            for recipient in RECIPIENTS
        ]
        results = await asyncio.gather(*tasks)
        for errors, message in results:
            assert not errors
            assert isinstance(errors, dict)
            assert message != ""


async def test_connect_and_sendmail_multiple_times_with_gather(
    hostname: str,
    smtpd_server_port: int,
    client_tls_context: ssl.SSLContext,
    sender_str: str,
    message_str: str,
) -> None:
    async def connect_and_send(
        *args: Any, **kwargs: Any
    ) -> tuple[dict[str, SMTPResponse], str]:
        async with SMTP(
            hostname=hostname, port=smtpd_server_port, tls_context=client_tls_context
        ) as client:
            response = await client.sendmail(*args, **kwargs)

        return response

    tasks = [
        connect_and_send(sender_str, [recipient], message_str)
        for recipient in RECIPIENTS
    ]
    results = await asyncio.gather(*tasks)
    for errors, message in results:
        assert not errors
        assert isinstance(errors, dict)
        assert message != ""


async def test_multiple_clients_with_gather(
    hostname: str,
    smtpd_server: asyncio.AbstractServer,
    smtpd_server_port: int,
    client_tls_context: ssl.SSLContext,
    sender_str: str,
    message_str: str,
) -> None:
    async def connect_and_send(
        *args: Any, **kwargs: Any
    ) -> tuple[dict[str, SMTPResponse], str]:
        client = SMTP(
            hostname=hostname, port=smtpd_server_port, tls_context=client_tls_context
        )
        async with client:
            response = await client.sendmail(*args, **kwargs)

        return response

    tasks = [
        connect_and_send(sender_str, [recipient], message_str)
        for recipient in RECIPIENTS
    ]
    results = await asyncio.gather(*tasks)
    for errors, message in results:
        assert not errors
        assert isinstance(errors, dict)
        assert message != ""


async def test_multiple_actions_in_context_manager_with_gather(
    hostname: str,
    smtpd_server_port: int,
    client_tls_context: ssl.SSLContext,
    sender_str: str,
    message_str: str,
) -> None:
    async def connect_and_run_commands(*args: Any, **kwargs: Any) -> SMTPResponse:
        async with SMTP(
            hostname=hostname, port=smtpd_server_port, tls_context=client_tls_context
        ) as client:
            await client.ehlo()
            await client.help()
            response = await client.noop()

        return response

    tasks = [
        connect_and_run_commands(sender_str, [recipient], message_str)
        for recipient in RECIPIENTS
    ]
    responses = await asyncio.gather(*tasks)
    for response in responses:
        assert 200 <= response.code < 300


@pytest.mark.smtpd_mocks(smtp_EXPN=mock_response_expn)
async def test_many_commands_with_gather(smtp_client: SMTP) -> None:
    """
    Tests that appropriate locks are in place to prevent commands confusing each other.
    """
    async with smtp_client:
        tasks: list[Awaitable] = [
            smtp_client.ehlo(),
            smtp_client.helo(),
            smtp_client.noop(),
            smtp_client.vrfy("foo@bar.com"),
            smtp_client.expn("users@example.com"),
            smtp_client.mail("alice@example.com"),
            smtp_client.help(),
        ]
        results = await asyncio.gather(*tasks)

    for result in results[:-1]:
        assert 200 <= result.code < 300

    # Help text is returned as a string, not a result tuple
    assert "Supported commands" in results[-1]


async def test_close_works_on_stopped_loop(
    hostname: str,
    smtpd_server_port: int,
    client_tls_context: ssl.SSLContext,
) -> None:
    event_loop = asyncio.get_running_loop()
    client = SMTP(
        hostname=hostname, port=smtpd_server_port, tls_context=client_tls_context
    )

    await client.connect()
    assert client.is_connected
    assert client.transport is not None

    event_loop.stop()

    client.close()
    assert not client.is_connected


async def test_context_manager_entry_multiple_times_with_gather(
    smtp_client: SMTP, sender_str: str, message_str: str
) -> None:
    async def connect_and_send(
        *args: Any, **kwargs: Any
    ) -> tuple[dict[str, SMTPResponse], str]:
        async with smtp_client:
            response = await smtp_client.sendmail(*args, **kwargs)

        return response

    tasks = [
        asyncio.wait_for(connect_and_send(sender_str, [recipient], message_str), 2.0)
        for recipient in RECIPIENTS
    ]
    results = await asyncio.gather(*tasks)
    for errors, message in results:
        assert not errors
        assert isinstance(errors, dict)
        assert message != ""

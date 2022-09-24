"""
Sync method tests.
"""
import asyncio
import email.message
from typing import NoReturn

import pytest

from aiosmtplib import SMTP
from aiosmtplib.sync import async_to_sync


def test_sendmail_sync(
    event_loop: asyncio.AbstractEventLoop,
    smtp_client_threaded: SMTP,
    sender_str: str,
    recipient_str: str,
    message_str: str,
) -> None:
    errors, response = smtp_client_threaded.sendmail_sync(
        sender_str, [recipient_str], message_str
    )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_sendmail_sync_when_connected(
    event_loop: asyncio.AbstractEventLoop,
    smtp_client_threaded: SMTP,
    sender_str: str,
    recipient_str: str,
    message_str: str,
) -> None:
    event_loop.run_until_complete(smtp_client_threaded.connect())

    errors, response = smtp_client_threaded.sendmail_sync(
        sender_str, [recipient_str], message_str
    )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_send_message_sync(
    event_loop: asyncio.AbstractEventLoop,
    smtp_client_threaded: SMTP,
    message: email.message.Message,
) -> None:
    errors, response = smtp_client_threaded.send_message_sync(message)

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_send_message_sync_when_connected(
    event_loop: asyncio.AbstractEventLoop,
    smtp_client_threaded: SMTP,
    message: email.message.Message,
) -> None:
    event_loop.run_until_complete(smtp_client_threaded.connect())

    errors, response = smtp_client_threaded.send_message_sync(message)

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_async_to_sync_without_loop(event_loop: asyncio.AbstractEventLoop) -> None:
    async def test_func() -> int:
        return 7

    result = async_to_sync(test_func())

    assert result == 7


def test_async_to_sync_with_exception(event_loop: asyncio.AbstractEventLoop) -> None:
    async def test_func() -> NoReturn:
        raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        async_to_sync(test_func(), loop=event_loop)


@pytest.mark.asyncio
async def test_async_to_sync_with_running_loop(
    event_loop: asyncio.AbstractEventLoop,
) -> None:
    async def test_func() -> None:
        return None

    with pytest.raises(RuntimeError):
        async_to_sync(test_func())

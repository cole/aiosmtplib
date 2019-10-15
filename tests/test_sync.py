"""
Sync method tests.
"""
import pytest

from aiosmtplib.sync import async_to_sync


def test_sendmail_sync(
    event_loop, smtp_client_threaded, sender_str, recipient_str, message_str
):
    errors, response = smtp_client_threaded.sendmail_sync(
        sender_str, [recipient_str], message_str
    )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_sendmail_sync_when_connected(
    event_loop, smtp_client_threaded, sender_str, recipient_str, message_str
):
    event_loop.run_until_complete(smtp_client_threaded.connect())

    errors, response = smtp_client_threaded.sendmail_sync(
        sender_str, [recipient_str], message_str
    )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_send_message_sync(event_loop, smtp_client_threaded, message):
    errors, response = smtp_client_threaded.send_message_sync(message)

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_send_message_sync_when_connected(event_loop, smtp_client_threaded, message):
    event_loop.run_until_complete(smtp_client_threaded.connect())

    errors, response = smtp_client_threaded.send_message_sync(message)

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_async_to_sync_without_loop(event_loop):
    async def test_func():
        return 7

    result = async_to_sync(test_func())

    assert result == 7


def test_async_to_sync_with_exception(event_loop):
    async def test_func():
        raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        async_to_sync(test_func(), loop=event_loop)


@pytest.mark.asyncio
async def test_async_to_sync_with_running_loop(event_loop):
    with pytest.raises(RuntimeError):
        async_to_sync(None)

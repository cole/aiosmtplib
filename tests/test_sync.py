"""
Sync method tests.
"""
import pytest

from aiosmtplib.sync import async_to_sync

from .smtpd import SMTPDController


@pytest.fixture(scope="function")
def threaded_smtpd_server(request, bind_address, port, smtpd_handler):
    controller = SMTPDController(smtpd_handler, hostname=bind_address, port=port)
    controller.start()
    request.addfinalizer(controller.stop)

    return controller.server


def test_sendmail_sync(smtp_client, threaded_smtpd_server, message):
    errors, response = smtp_client.sendmail_sync(
        message["From"], [message["To"]], str(message)
    )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_sendmail_sync_when_connected(
    smtp_client, event_loop, threaded_smtpd_server, message
):
    event_loop.run_until_complete(smtp_client.connect())

    errors, response = smtp_client.sendmail_sync(
        message["From"], [message["To"]], str(message)
    )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_send_message_sync(smtp_client, threaded_smtpd_server, message):
    errors, response = smtp_client.send_message_sync(message)

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_send_message_sync_when_connected(
    smtp_client, event_loop, threaded_smtpd_server, message
):
    event_loop.run_until_complete(smtp_client.connect())

    errors, response = smtp_client.send_message_sync(message)

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

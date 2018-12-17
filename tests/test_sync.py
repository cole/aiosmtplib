"""
Sync method tests.
"""
import pytest
from aiosmtpd.controller import Controller


@pytest.fixture(scope="function")
def threaded_smtpd_server(request, hostname, port, smtpd_handler):
    controller = Controller(smtpd_handler, hostname=hostname, port=port)
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

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.handlers import Sink

from aiosmtplib import SMTP


@pytest.fixture(scope="function")
def threaded_smtpd_server(request, hostname, port):

    controller = Controller(Sink(), hostname=hostname, port=port)
    controller.start()
    request.addfinalizer(controller.stop)

    return controller.server


@pytest.fixture(scope="function")
def threaded_smtp_client(request, threaded_smtpd_server, event_loop, hostname, port):
    client = SMTP(hostname=hostname, port=port, loop=event_loop, timeout=1)

    return client


def test_sendmail_sync(threaded_smtp_client, message):
    errors, response = threaded_smtp_client.sendmail_sync(
        message["From"], [message["To"]], str(message)
    )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_sendmail_sync_when_connected(threaded_smtp_client, event_loop, message):
    event_loop.run_until_complete(threaded_smtp_client.connect())

    errors, response = threaded_smtp_client.sendmail_sync(
        message["From"], [message["To"]], str(message)
    )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


def test_send_message_sync(threaded_smtp_client, message):
    errors, response = threaded_smtp_client.send_message_sync(message)

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""

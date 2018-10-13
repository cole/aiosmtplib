import email.mime.multipart
import email.mime.text

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.handlers import Sink

from aiosmtplib import SMTP


@pytest.fixture()
def threaded_smtpd_server(request, hostname, port):

    controller = Controller(Sink(), hostname=hostname, port=port)
    controller.start()
    request.addfinalizer(controller.stop)

    return controller.server


@pytest.fixture()
def threaded_smtpd_client(request, threaded_smtpd_server, event_loop, hostname, port):
    client = SMTP(hostname=hostname, port=port, loop=event_loop, timeout=1)

    return client


def test_sendmail_sync(threaded_smtpd_client):
    test_address = "test@example.com"
    mail_text = """
    Hello world!

    -a tester
    """
    errors, message = threaded_smtpd_client.sendmail_sync(
        test_address, [test_address], mail_text
    )

    assert not errors
    assert isinstance(errors, dict)
    assert message != ""


def test_sendmail_sync_when_connected(threaded_smtpd_client, event_loop):
    test_address = "test@example.com"
    mail_text = "hello world"

    event_loop.run_until_complete(threaded_smtpd_client.connect())

    errors, message = threaded_smtpd_client.sendmail_sync(
        test_address, [test_address], mail_text
    )

    assert not errors
    assert isinstance(errors, dict)
    assert message != ""


def test_send_message_sync(threaded_smtpd_client):
    message = email.mime.multipart.MIMEMultipart()
    message["To"] = "test@example.com"
    message["From"] = "test@example.com"
    message["Subject"] = "tëst message"
    body = email.mime.text.MIMEText(
        """
    Hello world. UTF8 OK? 15£ ümläüts'r'us
    """
    )
    message.attach(body)

    errors, message = threaded_smtpd_client.send_message_sync(message)

    assert not errors
    assert isinstance(errors, dict)
    assert message != ""

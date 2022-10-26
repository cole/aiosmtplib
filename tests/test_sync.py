"""
Sync method tests.
"""
import email.message

from aiosmtplib import SMTP


def test_sendmail_sync(
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


def test_send_message_sync(
    smtp_client_threaded: SMTP,
    message: email.message.Message,
) -> None:
    errors, response = smtp_client_threaded.send_message_sync(message)

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""

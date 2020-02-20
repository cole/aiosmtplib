"""
SMTP.sendmail and SMTP.send_message method testing.
"""
import copy
import email.generator
import email.header

import pytest

from aiosmtplib import (
    SMTPNotSupported,
    SMTPRecipientsRefused,
    SMTPResponseException,
    SMTPStatus,
)
from aiosmtplib.email import formataddr

pytestmark = pytest.mark.asyncio()


async def test_sendmail_simple_success(
    smtp_client, smtpd_server, sender_str, recipient_str, message_str
):
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            sender_str, [recipient_str], message_str
        )

        assert not errors
        assert isinstance(errors, dict)
        assert response != ""


async def test_sendmail_binary_content(
    smtp_client, smtpd_server, sender_str, recipient_str, message_str
):
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            sender_str, [recipient_str], bytes(message_str, "ascii")
        )

        assert not errors
        assert isinstance(errors, dict)
        assert response != ""


async def test_sendmail_with_recipients_string(
    smtp_client, smtpd_server, sender_str, recipient_str, message_str
):
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            sender_str, recipient_str, message_str
        )

        assert not errors
        assert response != ""


async def test_sendmail_with_mail_option(
    smtp_client, smtpd_server, sender_str, recipient_str, message_str
):
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            sender_str, [recipient_str], message_str, mail_options=["BODY=8BITMIME"]
        )

        assert not errors
        assert response != ""


async def test_sendmail_without_size_option(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    sender_str,
    recipient_str,
    message_str,
    received_commands,
):
    response_handler = smtpd_response_handler_factory(
        "{} done".format(SMTPStatus.completed)
    )
    monkeypatch.setattr(smtpd_class, "smtp_EHLO", response_handler)

    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            sender_str, [recipient_str], message_str
        )

        assert not errors
        assert response != ""


async def test_sendmail_with_invalid_mail_option(
    smtp_client, smtpd_server, sender_str, recipient_str, message_str
):
    async with smtp_client:
        with pytest.raises(SMTPResponseException) as excinfo:
            await smtp_client.sendmail(
                sender_str,
                [recipient_str],
                message_str,
                mail_options=["BADDATA=0x00000000"],
            )

        assert excinfo.value.code == SMTPStatus.syntax_error


async def test_sendmail_with_rcpt_option(
    smtp_client, smtpd_server, sender_str, recipient_str, message_str
):
    async with smtp_client:
        with pytest.raises(SMTPRecipientsRefused) as excinfo:
            await smtp_client.sendmail(
                sender_str,
                [recipient_str],
                message_str,
                rcpt_options=["NOTIFY=FAILURE,DELAY"],
            )

        recipient_exc = excinfo.value.recipients[0]
        assert recipient_exc.code == SMTPStatus.syntax_error
        assert (
            recipient_exc.message
            == "RCPT TO parameters not recognized or not implemented"
        )


async def test_sendmail_simple_failure(smtp_client, smtpd_server):
    async with smtp_client:
        with pytest.raises(SMTPRecipientsRefused):
            #  @@ is an invalid recipient.
            await smtp_client.sendmail("test@example.com", ["@@"], "blah")


async def test_sendmail_error_silent_rset_handles_disconnect(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    sender_str,
    recipient_str,
    message_str,
):
    response_handler = smtpd_response_handler_factory(
        "{} error".format(SMTPStatus.unrecognized_parameters), close_after=True
    )
    monkeypatch.setattr(smtpd_class, "smtp_DATA", response_handler)

    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.sendmail(sender_str, [recipient_str], message_str)


async def test_rset_after_sendmail_error_response_to_mail(
    smtp_client, smtpd_server, received_commands
):
    """
    If an error response is given to the MAIL command in the sendmail method,
    test that we reset the server session.
    """
    async with smtp_client:
        response = await smtp_client.ehlo()
        assert response.code == SMTPStatus.completed

        with pytest.raises(SMTPResponseException) as excinfo:
            await smtp_client.sendmail(">foobar<", ["test@example.com"], "Hello World")

        assert excinfo.value.code == SMTPStatus.unrecognized_parameters
        assert received_commands[-1][0] == "RSET"


async def test_rset_after_sendmail_error_response_to_rcpt(
    smtp_client, smtpd_server, received_commands
):
    """
    If an error response is given to the RCPT command in the sendmail method,
    test that we reset the server session.
    """
    async with smtp_client:
        response = await smtp_client.ehlo()
        assert response.code == SMTPStatus.completed

        with pytest.raises(SMTPRecipientsRefused) as excinfo:
            await smtp_client.sendmail(
                "test@example.com", [">not an addr<"], "Hello World"
            )

        assert excinfo.value.recipients[0].code == SMTPStatus.unrecognized_parameters
        assert received_commands[-1][0] == "RSET"


async def test_rset_after_sendmail_error_response_to_data(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
    sender_str,
    recipient_str,
    message_str,
    received_commands,
):
    """
    If an error response is given to the DATA command in the sendmail method,
    test that we reset the server session.
    """
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_class, "smtp_DATA", response_handler)

    async with smtp_client:
        response = await smtp_client.ehlo()
        assert response.code == SMTPStatus.completed

        with pytest.raises(SMTPResponseException) as excinfo:
            await smtp_client.sendmail(sender_str, [recipient_str], message_str)

        assert excinfo.value.code == error_code
        assert received_commands[-1][0] == "RSET"


async def test_send_message(smtp_client, smtpd_server, message):
    async with smtp_client:
        errors, response = await smtp_client.send_message(message)

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


async def test_send_message_with_sender_and_recipient_args(
    smtp_client, smtpd_server, message, received_messages
):
    sender = "sender2@example.com"
    recipients = ["recipient1@example.com", "recipient2@example.com"]
    async with smtp_client:
        errors, response = await smtp_client.send_message(
            message, sender=sender, recipients=recipients
        )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""

    assert len(received_messages) == 1
    assert received_messages[0]["X-MailFrom"] == sender
    assert received_messages[0]["X-RcptTo"] == ", ".join(recipients)


async def test_send_multiple_messages_in_sequence(smtp_client, smtpd_server, message):
    message1 = copy.copy(message)

    message2 = copy.copy(message)
    del message2["To"]
    message2["To"] = "recipient2@example.com"

    async with smtp_client:
        errors1, response1 = await smtp_client.send_message(message1)

        assert not errors1
        assert isinstance(errors1, dict)
        assert response1 != ""

        errors2, response2 = await smtp_client.send_message(message2)

        assert not errors2
        assert isinstance(errors2, dict)
        assert response2 != ""


async def test_send_message_without_recipients(smtp_client, smtpd_server, message):
    del message["To"]

    async with smtp_client:
        with pytest.raises(ValueError):
            await smtp_client.send_message(message)


async def test_send_message_without_sender(smtp_client, smtpd_server, message):
    del message["From"]

    async with smtp_client:
        with pytest.raises(ValueError):
            await smtp_client.send_message(message)


async def test_send_message_smtputf8_sender(
    smtp_client_smtputf8,
    smtpd_server_smtputf8,
    message,
    received_commands,
    received_messages,
):
    del message["From"]
    message["From"] = "séndër@exåmple.com"

    async with smtp_client_smtputf8:
        errors, response = await smtp_client_smtputf8.send_message(message)

    assert not errors
    assert response != ""

    assert received_commands[1][0] == "MAIL"
    assert received_commands[1][1] == message["From"]
    # Size varies depending on the message type
    assert received_commands[1][2][0].startswith("SIZE=")
    assert received_commands[1][2][1:] == ["SMTPUTF8", "BODY=8BITMIME"]

    assert len(received_messages) == 1
    assert received_messages[0]["X-MailFrom"] == message["From"]


async def test_send_mime_message_smtputf8_recipient(
    smtp_client_smtputf8,
    smtpd_server_smtputf8,
    mime_message,
    received_commands,
    received_messages,
):
    mime_message["To"] = "reçipïént@exåmple.com"

    async with smtp_client_smtputf8:
        errors, response = await smtp_client_smtputf8.send_message(mime_message)

    assert not errors
    assert response != ""

    assert received_commands[2][0] == "RCPT"
    assert received_commands[2][1] == mime_message["To"]

    assert len(received_messages) == 1
    assert received_messages[0]["X-RcptTo"] == ", ".join(mime_message.get_all("To"))


async def test_send_compat32_message_smtputf8_recipient(
    smtp_client_smtputf8,
    smtpd_server_smtputf8,
    compat32_message,
    received_commands,
    received_messages,
):
    recipient_bytes = bytes("reçipïént@exåmple.com", "utf-8")
    compat32_message["To"] = email.header.Header(recipient_bytes, "utf-8")

    async with smtp_client_smtputf8:
        errors, response = await smtp_client_smtputf8.send_message(compat32_message)

    assert not errors
    assert response != ""

    assert received_commands[2][0] == "RCPT"
    assert received_commands[2][1] == compat32_message["To"]

    assert len(received_messages) == 1
    assert (
        received_messages[0]["X-RcptTo"]
        == "recipient@example.com, reçipïént@exåmple.com"
    )


async def test_send_message_smtputf8_not_supported(smtp_client, smtpd_server, message):
    message["To"] = "reçipïént2@exåmple.com"

    async with smtp_client:
        with pytest.raises(SMTPNotSupported):
            await smtp_client.send_message(message)


async def test_send_message_with_formataddr(smtp_client, smtpd_server, message):
    message["To"] = formataddr(("æøå", "someotheruser@example.com"))

    async with smtp_client:
        errors, response = await smtp_client.send_message(message)

    assert not errors
    assert response != ""


async def test_send_compat32_message_utf8_text_without_smtputf8(
    smtp_client, smtpd_server, compat32_message, received_commands, received_messages
):
    compat32_message["To"] = email.header.Header(
        "reçipïént <recipient2@example.com>", "utf-8"
    )

    async with smtp_client:
        errors, response = await smtp_client.send_message(compat32_message)

    assert not errors
    assert response != ""

    assert received_commands[2][0] == "RCPT"
    assert received_commands[2][1] == compat32_message["To"].encode()

    assert len(received_messages) == 1
    assert (
        received_messages[0]["X-RcptTo"]
        == "recipient@example.com, recipient2@example.com"
    )
    # Name should be encoded
    assert received_messages[0].get_all("To") == [
        "recipient@example.com",
        "=?utf-8?b?cmXDp2lww6/DqW50IDxyZWNpcGllbnQyQGV4YW1wbGUuY29tPg==?=",
    ]


async def test_send_mime_message_utf8_text_without_smtputf8(
    smtp_client, smtpd_server, mime_message, received_commands, received_messages
):
    mime_message["To"] = "reçipïént <recipient2@example.com>"

    async with smtp_client:
        errors, response = await smtp_client.send_message(mime_message)

    assert not errors
    assert response != ""

    assert received_commands[2][0] == "RCPT"
    assert received_commands[2][1] == mime_message["To"]

    assert len(received_messages) == 1
    assert (
        received_messages[0]["X-RcptTo"]
        == "recipient@example.com, recipient2@example.com"
    )
    # Name should be encoded
    assert received_messages[0].get_all("To") == [
        "recipient@example.com",
        "=?utf-8?b?cmXDp2lww6/DqW50IDxyZWNpcGllbnQyQGV4YW1wbGUuY29tPg==?=",
    ]


async def test_sendmail_empty_sender(
    smtp_client, smtpd_server, recipient_str, message_str
):
    async with smtp_client:
        errors, response = await smtp_client.sendmail("", [recipient_str], message_str)

        assert not errors
        assert isinstance(errors, dict)
        assert response != ""

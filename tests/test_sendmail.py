"""
SMTP.sendmail and SMTP.send_message method testing.
"""

import copy
import email.generator
import email.header
import email.message
from typing import Any, Optional

import pytest

from aiosmtplib import (
    SMTP,
    SMTPNotSupported,
    SMTPRecipientsRefused,
    SMTPResponseException,
    SMTPStatus,
)

from .smtpd import (
    mock_response_done,
    mock_response_error_disconnect,
    mock_response_bad_command_sequence,
)


async def test_sendmail_simple_success(
    smtp_client: SMTP,
    sender_str: str,
    recipient_str: str,
    message_str: str,
) -> None:
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            sender_str, [recipient_str], message_str
        )

        assert not errors
        assert isinstance(errors, dict)
        assert response != ""


async def test_sendmail_binary_content(
    smtp_client: SMTP,
    sender_str: str,
    recipient_str: str,
    message_str: str,
) -> None:
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            sender_str, [recipient_str], bytes(message_str, "ascii")
        )

        assert not errors
        assert isinstance(errors, dict)
        assert response != ""


async def test_sendmail_with_recipients_string(
    smtp_client: SMTP,
    sender_str: str,
    recipient_str: str,
    message_str: str,
) -> None:
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            sender_str, recipient_str, message_str
        )

        assert not errors
        assert response != ""


async def test_sendmail_with_mail_option(
    smtp_client: SMTP,
    sender_str: str,
    recipient_str: str,
    message_str: str,
) -> None:
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            sender_str, [recipient_str], message_str, mail_options=["BODY=8BITMIME"]
        )

        assert not errors
        assert response != ""


@pytest.mark.smtpd_mocks(smtp_EHLO=mock_response_done)
async def test_sendmail_without_size_option(
    smtp_client: SMTP,
    sender_str: str,
    recipient_str: str,
    message_str: str,
) -> None:
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            sender_str, [recipient_str], message_str
        )

        assert not errors
        assert response != ""


async def test_sendmail_with_invalid_mail_option(
    smtp_client: SMTP,
    sender_str: str,
    recipient_str: str,
    message_str: str,
) -> None:
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
    smtp_client: SMTP,
    sender_str: str,
    recipient_str: str,
    message_str: str,
) -> None:
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


async def test_sendmail_simple_failure(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPRecipientsRefused):
            #  @@ is an invalid recipient.
            await smtp_client.sendmail("test@example.com", ["@@"], "blah")


async def test_sendmail_smtputf8_not_supported(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPNotSupported, match="SMTPUTF8 is not supported"):
            await smtp_client.sendmail(
                "test@example.com",
                ["børk@example.com"],
                "blah",
                mail_options=["SMTPUTF8"],
            )


@pytest.mark.smtpd_mocks(smtp_DATA=mock_response_error_disconnect)
async def test_sendmail_error_silent_rset_handles_disconnect(
    smtp_client: SMTP,
    sender_str: str,
    recipient_str: str,
    message_str: str,
) -> None:
    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.sendmail(sender_str, [recipient_str], message_str)


async def test_rset_after_sendmail_error_response_to_mail(
    smtp_client: SMTP,
    received_commands: list[tuple[str, tuple[Any, ...]]],
) -> None:
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
    smtp_client: SMTP,
    received_commands: list[tuple[str, tuple[Any, ...]]],
) -> None:
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


@pytest.mark.smtpd_mocks(smtp_DATA=mock_response_bad_command_sequence)
async def test_rset_after_sendmail_error_response_to_data(
    smtp_client: SMTP,
    sender_str: str,
    recipient_str: str,
    message_str: str,
    received_commands: list[tuple[str, tuple[Any, ...]]],
) -> None:
    """
    If an error response is given to the DATA command in the sendmail method,
    test that we reset the server session.
    """
    async with smtp_client:
        response = await smtp_client.ehlo()
        assert response.code == SMTPStatus.completed

        with pytest.raises(SMTPResponseException) as excinfo:
            await smtp_client.sendmail(sender_str, [recipient_str], message_str)

        assert excinfo.value.code == SMTPStatus.bad_command_sequence
        assert received_commands[-1][0] == "RSET"


async def test_send_message(smtp_client: SMTP, message: email.message.Message) -> None:
    async with smtp_client:
        errors, response = await smtp_client.send_message(message)

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


async def test_send_message_with_sender_and_recipient_args(
    smtp_client: SMTP,
    message: email.message.Message,
    received_messages: list[email.message.EmailMessage],
) -> None:
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


async def test_send_message_with_cc_recipients(
    smtp_client: SMTP,
    recipient_str: str,
    message: email.message.Message,
    received_messages: list[email.message.EmailMessage],
    received_commands: list[tuple[str, tuple[Any, ...]]],
) -> None:
    cc_recipients = ["recipient1@example.com", "recipient2@example.com"]
    message["Cc"] = ", ".join(cc_recipients)

    async with smtp_client:
        errors, _ = await smtp_client.send_message(message)

    assert not errors

    assert len(received_messages) == 1
    assert (
        received_messages[0]["X-RcptTo"]
        == f"{recipient_str}, {', '.join(cc_recipients)}"
    )

    assert received_commands[2][0] == "RCPT"
    assert received_commands[2][1][0] == recipient_str
    assert received_commands[3][0] == "RCPT"
    assert received_commands[3][1][0] == cc_recipients[0]
    assert received_commands[4][0] == "RCPT"
    assert received_commands[4][1][0] == cc_recipients[1]


async def test_send_message_with_bcc_recipients(
    smtp_client: SMTP,
    recipient_str: str,
    message: email.message.Message,
    received_messages: list[email.message.EmailMessage],
    received_commands: list[tuple[str, tuple[Any, ...]]],
) -> None:
    bcc_recipients = ["recipient1@example.com", "recipient2@example.com"]
    message["Bcc"] = ", ".join(bcc_recipients)

    async with smtp_client:
        errors, _ = await smtp_client.send_message(message)

    assert not errors

    assert len(received_messages) == 1

    assert received_commands[2][0] == "RCPT"
    assert received_commands[2][1][0] == recipient_str
    assert received_commands[3][0] == "RCPT"
    assert received_commands[3][1][0] == bcc_recipients[0]
    assert received_commands[4][0] == "RCPT"
    assert received_commands[4][1][0] == bcc_recipients[1]


async def test_send_message_with_cc_and_bcc_recipients(
    smtp_client: SMTP,
    recipient_str: str,
    message: email.message.Message,
    received_messages: list[email.message.EmailMessage],
    received_commands: list[tuple[str, tuple[Any, ...]]],
) -> None:
    cc_recipient = "recipient2@example.com"
    message["Cc"] = cc_recipient
    bcc_recipient = "recipient2@example.com"
    message["Bcc"] = bcc_recipient

    async with smtp_client:
        errors, _ = await smtp_client.send_message(message)

    assert not errors

    assert len(received_messages) == 1
    assert received_messages[0]["To"] == recipient_str
    assert received_messages[0]["Cc"] == cc_recipient
    # BCC shouldn't be passed through
    assert received_messages[0]["Bcc"] is None

    assert received_commands[2][0] == "RCPT"
    assert received_commands[2][1][0] == recipient_str
    assert received_commands[3][0] == "RCPT"
    assert received_commands[3][1][0] == cc_recipient
    assert received_commands[4][0] == "RCPT"
    assert received_commands[4][1][0] == bcc_recipient


async def test_send_message_recipient_str(
    smtp_client: SMTP,
    message: email.message.Message,
    received_commands: list[tuple[str, tuple[Any, ...]]],
) -> None:
    recipient_str = "1234@example.org"
    async with smtp_client:
        errors, response = await smtp_client.send_message(
            message, recipients=recipient_str
        )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""
    assert received_commands[2][1][0] == recipient_str


async def test_send_message_mail_options(
    smtp_client: SMTP,
    message: email.message.Message,
) -> None:
    async with smtp_client:
        errors, response = await smtp_client.send_message(
            message, mail_options=["BODY=8BITMIME"]
        )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


async def test_send_multiple_messages_in_sequence(
    smtp_client: SMTP, message: email.message.Message
) -> None:
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


async def test_send_message_without_recipients(
    smtp_client: SMTP, message: email.message.Message
) -> None:
    del message["To"]

    async with smtp_client:
        with pytest.raises(ValueError):
            await smtp_client.send_message(message)


async def test_send_message_without_sender(
    smtp_client: SMTP, message: email.message.Message
) -> None:
    del message["From"]

    async with smtp_client:
        with pytest.raises(ValueError):
            await smtp_client.send_message(message)


@pytest.mark.smtpd_options(smtputf8=True)
async def test_send_message_smtputf8_sender(
    smtp_client: SMTP,
    message: email.message.Message,
    received_commands: list[tuple[str, tuple[Any, ...]]],
    received_messages: list[email.message.EmailMessage],
) -> None:
    del message["From"]
    message["From"] = "séndër@exåmple.com"

    async with smtp_client:
        errors, response = await smtp_client.send_message(message)

    assert not errors
    assert response != ""

    assert received_commands[1][0] == "MAIL"
    assert received_commands[1][1][0] == message["From"]
    # Size varies depending on the message type
    assert received_commands[1][1][1][0].startswith("SIZE=")
    assert received_commands[1][1][1][1:] == ["SMTPUTF8", "BODY=8BITMIME"]

    assert len(received_messages) == 1
    assert received_messages[0]["X-MailFrom"] == message["From"]


@pytest.mark.smtpd_options(smtputf8=True)
@pytest.mark.parametrize(
    "mail_options",
    (None, ["SMTPUTF8"]),
    ids=("no_mail_options", "smtputf8_option"),
)
async def test_send_mime_message_smtputf8_recipient(
    smtp_client: SMTP,
    mime_message: email.message.EmailMessage,
    received_commands: list[tuple[str, tuple[Any, ...]]],
    received_messages: list[email.message.EmailMessage],
    mail_options: Optional[list[str]],
) -> None:
    mime_message["To"] = "reçipïént@exåmple.com"

    async with smtp_client:
        errors, response = await smtp_client.send_message(
            mime_message, mail_options=mail_options
        )

    assert not errors
    assert response != ""

    assert received_commands[2][0] == "RCPT"
    assert received_commands[2][1][0] == mime_message["To"]

    assert len(received_messages) == 1
    assert received_messages[0]["X-RcptTo"] == ", ".join(mime_message.get_all("To"))


@pytest.mark.smtpd_options(smtputf8=True)
async def test_send_compat32_message_smtputf8_recipient(
    smtp_client: SMTP,
    compat32_message: email.message.Message,
    received_commands: list[tuple[str, tuple[Any, ...]]],
    received_messages: list[email.message.EmailMessage],
) -> None:
    recipient_bytes = bytes("reçipïént@exåmple.com", "utf-8")
    compat32_message["To"] = email.header.Header(recipient_bytes, "utf-8")

    async with smtp_client:
        errors, response = await smtp_client.send_message(compat32_message)

    assert not errors
    assert response != ""

    assert received_commands[2][0] == "RCPT"
    assert received_commands[2][1][0] == compat32_message["To"]

    assert len(received_messages) == 1
    assert (
        received_messages[0]["X-RcptTo"]
        == "recipient@example.com, reçipïént@exåmple.com"
    )


@pytest.mark.smtpd_options(smtputf8=False)
async def test_send_message_smtputf8_not_supported(
    smtp_client: SMTP, message: email.message.Message
) -> None:
    message["To"] = "reçipïént2@exåmple.com"

    async with smtp_client:
        with pytest.raises(SMTPNotSupported):
            await smtp_client.send_message(message)


@pytest.mark.smtpd_options(smtputf8=False)
async def test_send_compat32_message_utf8_text_without_smtputf8(
    smtp_client: SMTP,
    compat32_message: email.message.Message,
    received_commands: list[tuple[str, tuple[Any, ...]]],
    received_messages: list[email.message.EmailMessage],
) -> None:
    compat32_message["To"] = email.header.Header(
        "reçipïént <recipient2@example.com>", "utf-8"
    )

    async with smtp_client:
        errors, response = await smtp_client.send_message(compat32_message)

    assert not errors
    assert response != ""

    assert received_commands[2][0] == "RCPT"
    assert received_commands[2][1][0] == compat32_message["To"].encode()

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


@pytest.mark.smtpd_options(smtputf8=False)
async def test_send_mime_message_utf8_text_without_smtputf8(
    smtp_client: SMTP,
    mime_message: email.message.EmailMessage,
    received_commands: list[tuple[str, tuple[Any, ...]]],
    received_messages: list[email.message.EmailMessage],
) -> None:
    mime_message["To"] = "reçipïént <recipient2@example.com>"

    async with smtp_client:
        errors, response = await smtp_client.send_message(mime_message)

    assert not errors
    assert response != ""

    assert received_commands[2][0] == "RCPT"
    assert received_commands[2][1][0] == mime_message["To"]

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


@pytest.mark.smtpd_options(**{"smtputf8": False, "7bit": True})
async def test_send_message_7bit(
    smtp_client: SMTP,
    message: email.message.Message,
    received_commands: list[tuple[str, tuple[Any, ...]]],
) -> None:
    async with smtp_client:
        errors, response = await smtp_client.send_message(message)

    assert not errors
    assert response != ""

    assert "BODY=8BITMIME" not in received_commands[1][1][1]


async def test_sendmail_empty_sender(
    smtp_client: SMTP, recipient_str: str, message_str: str
) -> None:
    async with smtp_client:
        errors, response = await smtp_client.sendmail("", [recipient_str], message_str)

        assert not errors
        assert isinstance(errors, dict)
        assert response != ""

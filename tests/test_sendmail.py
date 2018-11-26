"""
sendmail and send_message method testing.
"""
import copy
import email.mime.multipart
import email.mime.text

import pytest

from aiosmtplib import SMTPRecipientsRefused, SMTPResponseException, SMTPStatus


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_sendmail_simple_success(smtpd_client, message):
    async with smtpd_client:
        errors, message = await smtpd_client.sendmail(
            message["From"], [message["To"]], str(message)
        )

        assert not errors
        assert isinstance(errors, dict)
        assert message != ""


async def test_sendmail_binary_content(smtpd_client, message):
    async with smtpd_client:
        errors, message = await smtpd_client.sendmail(
            message["From"], [message["To"]], bytes(str(message), "ascii")
        )

        assert not errors
        assert isinstance(errors, dict)
        assert message != ""


async def test_sendmail_with_recipients_string(smtpd_client, message):
    async with smtpd_client:
        errors, message = await smtpd_client.sendmail(
            message["From"], message["To"], str(message)
        )

        assert not errors
        assert message != ""


async def test_sendmail_with_mail_option(preset_client, message):
    async with preset_client:
        preset_client.server.responses.append(b"250 Hello there")
        preset_client.server.responses.append(b"250 ok")
        preset_client.server.responses.append(b"250 ok")
        preset_client.server.responses.append(b"354 go ahead")
        preset_client.server.responses.append(b"250 ok")

        errors, message = await preset_client.sendmail(
            message["From"], [message["To"]], str(message), mail_options=["SMTPUTF8"]
        )

        assert not errors
        assert message != ""


async def test_sendmail_with_rcpt_option(preset_client, message):
    async with preset_client:
        preset_client.server.responses.append(b"250 Hello there")
        preset_client.server.responses.append(b"250 ok")
        preset_client.server.responses.append(b"250 ok")
        preset_client.server.responses.append(b"354 go ahead")
        preset_client.server.responses.append(b"250 ok")

        errors, message = await preset_client.sendmail(
            message["From"],
            [message["To"]],
            str(message),
            rcpt_options=["NOTIFY=FAILURE,DELAY"],
        )

        assert not errors
        assert message != ""


async def test_sendmail_simple_failure(smtpd_client):
    async with smtpd_client:
        with pytest.raises(SMTPRecipientsRefused):
            #  @@ is an invalid recipient.
            await smtpd_client.sendmail("test@example.com", ["@@"], "blah")


async def test_sendmail_error_silent_rset_handles_disconnect(preset_client, message):
    async with preset_client:
        preset_client.server.responses.append(b"250 Hello there")

        preset_client.server.goodbye = b"501 oh noes"
        with pytest.raises(SMTPResponseException):
            await preset_client.sendmail(message["From"], [message["To"]], str(message))


async def test_rset_after_sendmail_error_response_to_mail(preset_client):
    """
    If an error response is given to the MAIL command in the sendmail method,
    test that we reset the server session.
    """
    async with preset_client:
        preset_client.server.responses.append(b"250 Hello there")
        response = await preset_client.ehlo()
        assert response.code == SMTPStatus.completed

        preset_client.server.responses.append(b"501 bad address")
        preset_client.server.responses.append(b"250 ok")

        try:
            await preset_client.sendmail(
                ">foobar<", ["test@example.com"], "Hello World"
            )
        except SMTPResponseException as err:
            assert err.code == 501
            assert preset_client.server.requests[-1][:4] == b"RSET"


async def test_rset_after_sendmail_error_response_to_rcpt(preset_client):
    """
    If an error response is given to the RCPT command in the sendmail method,
    test that we reset the server session.
    """
    async with preset_client:
        preset_client.server.responses.append(b"250 Hello there")
        response = await preset_client.ehlo()
        assert response.code == SMTPStatus.completed

        preset_client.server.responses.append(b"250 ok")
        preset_client.server.responses.append(b"501 bad address")
        preset_client.server.responses.append(b"250 ok")

        try:
            await preset_client.sendmail(
                "test@example.com", [">not an addr<"], "Hello World"
            )
        except SMTPRecipientsRefused as err:
            assert err.recipients[0].code == 501
            assert preset_client.server.requests[-1][:4] == b"RSET"


async def test_rset_after_sendmail_error_response_to_data(preset_client, message):
    """
    If an error response is given to the DATA command in the sendmail method,
    test that we reset the server session.
    """
    async with preset_client:
        preset_client.server.responses.append(b"250 Hello there")
        response = await preset_client.ehlo()
        assert response.code == SMTPStatus.completed

        preset_client.server.responses.append(b"250 ok")
        preset_client.server.responses.append(b"250 ok")
        preset_client.server.responses.append(b"501 bad data")
        preset_client.server.responses.append(b"250 ok")

        try:
            await preset_client.sendmail(message["From"], [message["To"]], str(message))
        except SMTPResponseException as err:
            assert err.code == 501
            assert preset_client.server.requests[-1][:4] == b"RSET"


async def test_send_message(smtpd_client, message):
    async with smtpd_client:
        errors, response = await smtpd_client.send_message(message)

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


async def test_send_message_with_sender_and_recipient_args(
    smtpd_client, message, recieved_messages
):
    sender = "sender2@example.com"
    recipients = ["recipient1@example.com", "recipient2@example.com"]
    async with smtpd_client:
        errors, response = await smtpd_client.send_message(
            message, sender=sender, recipients=recipients
        )

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""

    assert len(recieved_messages) == 1
    assert recieved_messages[0]["X-MailFrom"] == sender
    assert recieved_messages[0]["X-RcptTo"] == ", ".join(recipients)


async def test_send_multiple_messages_in_sequence(smtpd_client, message):
    message1 = copy.copy(message)

    message2 = copy.copy(message)
    del message2["To"]
    message2["To"] = "recipient2@example.com"

    async with smtpd_client:
        errors1, message1 = await smtpd_client.send_message(message1)

        assert not errors1
        assert isinstance(errors1, dict)
        assert message1 != ""

        errors2, message2 = await smtpd_client.send_message(message2)

        assert not errors2
        assert isinstance(errors2, dict)
        assert message2 != ""

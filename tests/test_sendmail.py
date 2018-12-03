"""
sendmail and send_message method testing.
"""
import copy

import pytest

from aiosmtplib import SMTPRecipientsRefused, SMTPResponseException, SMTPStatus


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_sendmail_simple_success(smtpd_client, message):
    async with smtpd_client:
        errors, response = await smtpd_client.sendmail(
            message["From"], [message["To"]], str(message)
        )

        assert not errors
        assert isinstance(errors, dict)
        assert response != ""


async def test_sendmail_binary_content(smtpd_client, message):
    async with smtpd_client:
        errors, response = await smtpd_client.sendmail(
            message["From"], [message["To"]], bytes(str(message), "ascii")
        )

        assert not errors
        assert isinstance(errors, dict)
        assert response != ""


async def test_sendmail_with_recipients_string(smtpd_client, message):
    async with smtpd_client:
        errors, response = await smtpd_client.sendmail(
            message["From"], message["To"], str(message)
        )

        assert not errors
        assert response != ""


async def test_sendmail_with_mail_option(smtpd_client, message):
    async with smtpd_client:
        errors, response = await smtpd_client.sendmail(
            message["From"],
            [message["To"]],
            str(message),
            mail_options=["BODY=8BITMIME"],
        )

        assert not errors
        assert response != ""


async def test_sendmail_with_invalid_mail_option(smtpd_client, message):
    async with smtpd_client:
        with pytest.raises(SMTPResponseException) as err:
            await smtpd_client.sendmail(
                message["From"],
                [message["To"]],
                str(message),
                mail_options=["BADDATA=0x00000000"],
            )

            assert err.code == SMTPStatus.syntax_error


async def test_sendmail_with_rcpt_option(smtpd_client, message):
    async with smtpd_client:
        errors, response = await smtpd_client.sendmail(
            message["From"],
            [message["To"]],
            str(message),
            rcpt_options=["NOTIFY=FAILURE,DELAY"],
        )

        assert not errors
        assert response != ""


async def test_sendmail_simple_failure(smtpd_client):
    async with smtpd_client:
        with pytest.raises(SMTPRecipientsRefused):
            #  @@ is an invalid recipient.
            await smtpd_client.sendmail("test@example.com", ["@@"], "blah")


async def test_sendmail_error_silent_rset_handles_disconnect(
    smtpd_client, message, smtpd_handler, smtpd_server, monkeypatch
):
    async def data_response(*args):
        smtpd_server.close()
        await smtpd_server.wait_closed()

        return "501 oh noes"

    monkeypatch.setattr(smtpd_handler, "handle_DATA", data_response, raising=False)

    async with smtpd_client:
        with pytest.raises(SMTPResponseException):
            await smtpd_client.sendmail(message["From"], [message["To"]], str(message))


async def test_rset_after_sendmail_error_response_to_mail(smtpd_client, smtpd_commands):
    """
    If an error response is given to the MAIL command in the sendmail method,
    test that we reset the server session.
    """
    async with smtpd_client:
        response = await smtpd_client.ehlo()
        assert response.code == SMTPStatus.completed

        try:
            await smtpd_client.sendmail(">foobar<", ["test@example.com"], "Hello World")
        except SMTPResponseException as err:
            assert err.code == SMTPStatus.unrecognized_parameters
            assert smtpd_commands[-1][0] == "RSET"


async def test_rset_after_sendmail_error_response_to_rcpt(smtpd_client, smtpd_commands):
    """
    If an error response is given to the RCPT command in the sendmail method,
    test that we reset the server session.
    """
    async with smtpd_client:
        response = await smtpd_client.ehlo()
        assert response.code == SMTPStatus.completed

        try:
            await smtpd_client.sendmail(
                "test@example.com", [">not an addr<"], "Hello World"
            )
        except SMTPRecipientsRefused as err:
            assert err.recipients[0].code == SMTPStatus.unrecognized_parameters
            assert smtpd_commands[-1][0] == "RSET"


async def test_rset_after_sendmail_error_response_to_data(
    smtpd_client, message, smtpd_commands, smtpd_handler, monkeypatch
):
    """
    If an error response is given to the DATA command in the sendmail method,
    test that we reset the server session.
    """

    async def data_response(*args):
        return "501 oh noes"

    monkeypatch.setattr(smtpd_handler, "handle_DATA", data_response, raising=False)

    async with smtpd_client:
        response = await smtpd_client.ehlo()
        assert response.code == SMTPStatus.completed

        try:
            await smtpd_client.sendmail(message["From"], [message["To"]], str(message))
        except SMTPResponseException as err:
            assert err.code == SMTPStatus.unrecognized_parameters
            assert smtpd_commands[-1][0] == "RSET"


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
        errors1, response1 = await smtpd_client.send_message(message1)

        assert not errors1
        assert isinstance(errors1, dict)
        assert response1 != ""

        errors2, response2 = await smtpd_client.send_message(message2)

        assert not errors2
        assert isinstance(errors2, dict)
        assert response2 != ""

"""
sendmail and send_message method testing.
"""
import copy

import pytest

from aiosmtplib import SMTPRecipientsRefused, SMTPResponseException, SMTPStatus


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_sendmail_simple_success(smtp_client, smtpd_server, message):
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            message["From"], [message["To"]], str(message)
        )

        assert not errors
        assert isinstance(errors, dict)
        assert response != ""


async def test_sendmail_binary_content(smtp_client, smtpd_server, message):
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            message["From"], [message["To"]], bytes(str(message), "ascii")
        )

        assert not errors
        assert isinstance(errors, dict)
        assert response != ""


async def test_sendmail_with_recipients_string(smtp_client, smtpd_server, message):
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            message["From"], message["To"], str(message)
        )

        assert not errors
        assert response != ""


async def test_sendmail_with_mail_option(smtp_client, smtpd_server, message):
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            message["From"],
            [message["To"]],
            str(message),
            mail_options=["BODY=8BITMIME"],
        )

        assert not errors
        assert response != ""


async def test_sendmail_without_size_option(
    smtp_client, smtpd_server, message, smtpd_class, monkeypatch, recieved_commands
):
    async def ehlo_response(self, hostname):
        self.session.host_name = hostname
        await self.push("250 all good")

    monkeypatch.setattr(smtpd_class, "smtp_EHLO", ehlo_response)

    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            message["From"], [message["To"]], str(message)
        )

        assert not errors
        assert response != ""


async def test_sendmail_with_invalid_mail_option(smtp_client, smtpd_server, message):
    async with smtp_client:
        with pytest.raises(SMTPResponseException) as err:
            await smtp_client.sendmail(
                message["From"],
                [message["To"]],
                str(message),
                mail_options=["BADDATA=0x00000000"],
            )

            assert err.code == SMTPStatus.syntax_error


async def test_sendmail_with_rcpt_option(smtp_client, smtpd_server, message):
    async with smtp_client:
        errors, response = await smtp_client.sendmail(
            message["From"],
            [message["To"]],
            str(message),
            rcpt_options=["NOTIFY=FAILURE,DELAY"],
        )

        assert not errors
        assert response != ""


async def test_sendmail_simple_failure(smtp_client, smtpd_server):
    async with smtp_client:
        with pytest.raises(SMTPRecipientsRefused):
            #  @@ is an invalid recipient.
            await smtp_client.sendmail("test@example.com", ["@@"], "blah")


async def test_sendmail_error_silent_rset_handles_disconnect(
    smtp_client, smtpd_server, message, smtpd_class, monkeypatch
):
    async def data_response(self, *args):
        await self.push("501 oh noes")
        self.transport.close()

    monkeypatch.setattr(smtpd_class, "smtp_DATA", data_response)

    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.sendmail(message["From"], [message["To"]], str(message))


async def test_rset_after_sendmail_error_response_to_mail(
    smtp_client, smtpd_server, recieved_commands
):
    """
    If an error response is given to the MAIL command in the sendmail method,
    test that we reset the server session.
    """
    async with smtp_client:
        response = await smtp_client.ehlo()
        assert response.code == SMTPStatus.completed

        try:
            await smtp_client.sendmail(">foobar<", ["test@example.com"], "Hello World")
        except SMTPResponseException as err:
            assert err.code == SMTPStatus.unrecognized_parameters
            assert recieved_commands[-1][0] == "RSET"


async def test_rset_after_sendmail_error_response_to_rcpt(
    smtp_client, smtpd_server, recieved_commands
):
    """
    If an error response is given to the RCPT command in the sendmail method,
    test that we reset the server session.
    """
    async with smtp_client:
        response = await smtp_client.ehlo()
        assert response.code == SMTPStatus.completed

        try:
            await smtp_client.sendmail(
                "test@example.com", [">not an addr<"], "Hello World"
            )
        except SMTPRecipientsRefused as err:
            assert err.recipients[0].code == SMTPStatus.unrecognized_parameters
            assert recieved_commands[-1][0] == "RSET"


async def test_rset_after_sendmail_error_response_to_data(
    smtp_client, smtpd_server, message, recieved_commands, smtpd_handler, monkeypatch
):
    """
    If an error response is given to the DATA command in the sendmail method,
    test that we reset the server session.
    """
    monkeypatch.setattr(smtpd_handler, "DATA_response_message", "501 oh noes")

    async with smtp_client:
        response = await smtp_client.ehlo()
        assert response.code == SMTPStatus.completed

        try:
            await smtp_client.sendmail(message["From"], [message["To"]], str(message))
        except SMTPResponseException as err:
            assert err.code == SMTPStatus.unrecognized_parameters
            assert recieved_commands[-1][0] == "RSET"


async def test_send_message(smtp_client, smtpd_server, message):
    async with smtp_client:
        errors, response = await smtp_client.send_message(message)

    assert not errors
    assert isinstance(errors, dict)
    assert response != ""


async def test_send_message_with_sender_and_recipient_args(
    smtp_client, smtpd_server, message, recieved_messages
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

    assert len(recieved_messages) == 1
    assert recieved_messages[0]["X-MailFrom"] == sender
    assert recieved_messages[0]["X-RcptTo"] == ", ".join(recipients)


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

"""
sendmail and send_message method testing.
"""
import copy
import email.mime.multipart
import email.mime.text

import pytest

from aiosmtplib import SMTPRecipientsRefused, SMTPResponseException, SMTPStatus


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_sendmail_simple_success(smtpd_client):
    async with smtpd_client:
        test_address = 'test@example.com'
        mail_text = """
        Hello world!

        -a tester
        """
        errors, message = await smtpd_client.sendmail(
            test_address, [test_address], mail_text)

        assert not errors
        assert isinstance(errors, dict)
        assert message != ''


async def test_sendmail_binary_content(smtpd_client):
    async with smtpd_client:
        test_address = 'test@example.com'
        mail_text = b"""
        Hello world!

        -a tester
        """
        errors, message = await smtpd_client.sendmail(
            test_address, [test_address], mail_text)

        assert not errors
        assert isinstance(errors, dict)
        assert message != ''


async def test_sendmail_simple_failure(smtpd_client):
    async with smtpd_client:
        sender = 'test@example.com'
        recipient = '@@'
        mail_text = 'blah-blah-blah'

        with pytest.raises(SMTPRecipientsRefused):
            await smtpd_client.sendmail(sender, [recipient], mail_text)


async def test_sendmail_error_silent_rset_handles_disconnect(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'250 Hello there')

        preset_client.server.goodbye = b'501 oh noes'
        with pytest.raises(SMTPResponseException):
            await preset_client.sendmail(
                'test@example.com', ['test2@example.com'], 'Hello World')


async def test_rset_after_sendmail_error_response_to_mail(preset_client):
    """
    If an error response is given to the MAIL command in the sendmail method,
    test that we reset the server session.
    """
    async with preset_client:
        preset_client.server.responses.append(b'250 Hello there')
        response = await preset_client.ehlo()
        assert response.code == SMTPStatus.completed

        preset_client.server.responses.append(b'501 bad address')
        preset_client.server.responses.append(b'250 ok')

        try:
            await preset_client.sendmail(
                '>foobar<', ['test@example.com'], 'Hello World')
        except SMTPResponseException as err:
            assert err.code == 501
            assert preset_client.server.requests[-1][:4] == b'RSET'


async def test_rset_after_sendmail_error_response_to_rcpt(preset_client):
    """
    If an error response is given to the RCPT command in the sendmail method,
    test that we reset the server session.
    """
    async with preset_client:
        preset_client.server.responses.append(b'250 Hello there')
        response = await preset_client.ehlo()
        assert response.code == SMTPStatus.completed

        preset_client.server.responses.append(b'250 ok')
        preset_client.server.responses.append(b'501 bad address')
        preset_client.server.responses.append(b'250 ok')

        try:
            await preset_client.sendmail(
                'test@example.com', ['>not an addr<'], 'Hello World')
        except SMTPRecipientsRefused as err:
            assert err.recipients[0].code == 501
            assert preset_client.server.requests[-1][:4] == b'RSET'


async def test_rset_after_sendmail_error_response_to_data(preset_client):
    """
    If an error response is given to the DATA command in the sendmail method,
    test that we reset the server session.
    """
    async with preset_client:
        preset_client.server.responses.append(b'250 Hello there')
        response = await preset_client.ehlo()
        assert response.code == SMTPStatus.completed

        preset_client.server.responses.append(b'250 ok')
        preset_client.server.responses.append(b'250 ok')
        preset_client.server.responses.append(b'501 bad data')
        preset_client.server.responses.append(b'250 ok')

        try:
            await preset_client.sendmail(
                'test@example.com', ['test2@example.com'], 'Hello World')
        except SMTPResponseException as err:
            assert err.code == 501
            assert preset_client.server.requests[-1][:4] == b'RSET'


async def test_send_message(smtpd_client):
    message = email.mime.multipart.MIMEMultipart()
    message['To'] = 'test@example.com'
    message['From'] = 'test@example.com'
    message['Subject'] = 'tëst message'
    body = email.mime.text.MIMEText("""
    Hello world. UTF8 OK? 15£ ümläüts'r'us
    """)
    message.attach(body)

    async with smtpd_client:
        errors, message = await smtpd_client.send_message(message)

    assert not errors
    assert isinstance(errors, dict)
    assert message != ''


async def test_send_multiple_messages_in_sequence(smtpd_client):
    message1 = email.mime.multipart.MIMEMultipart()
    message1['To'] = 'recipient1@example.com'
    message1['From'] = 'test@example.com'
    message1['Subject'] = 'tëst message'
    body = email.mime.text.MIMEText("""
    Hello world. UTF8 OK? 15£ ümläüts'r'us
    """)
    message1.attach(body)

    message2 = copy.copy(message1)
    message2['To'] = 'recipient2@example.com'

    async with smtpd_client:
        errors1, message1 = await smtpd_client.send_message(message1)

        assert not errors1
        assert isinstance(errors1, dict)
        assert message1 != ''

        errors2, message2 = await smtpd_client.send_message(message2)

        assert not errors2
        assert isinstance(errors2, dict)
        assert message2 != ''

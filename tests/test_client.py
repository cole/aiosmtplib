import copy
import email.mime.multipart
import email.mime.text

import pytest

from aiosmtplib import SMTPResponseException


@pytest.mark.asyncio(forbid_global_loop=True)
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


@pytest.mark.asyncio(forbid_global_loop=True)
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


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_gibberish_raises_exception(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'sdfjlfwqejflqw\n')
        with pytest.raises(SMTPResponseException):
            await preset_client.noop()

import email.mime.text
import email.mime.multipart

import pytest

from aiosmtplib import SMTP, SMTPResponseException, SMTPRecipientsRefused


@pytest.mark.asyncio
async def test_helo_ok(aiosmtpd_client):
    await aiosmtpd_client.connect()
    code, message = await aiosmtpd_client.helo()

    assert 200 <= code <= 299


@pytest.mark.asyncio
async def test_ehlo_ok(aiosmtpd_client):
    await aiosmtpd_client.connect()
    code, message = await aiosmtpd_client.ehlo()

    assert 200 <= code <= 299


@pytest.mark.asyncio
async def test_rset_ok(aiosmtpd_client):
    await aiosmtpd_client.connect()
    code, message = await aiosmtpd_client.rset()

    assert 200 <= code <= 299
    assert message == 'OK'


@pytest.mark.asyncio
async def test_noop_ok(aiosmtpd_client):
    await aiosmtpd_client.connect()
    code, message = await aiosmtpd_client.noop()

    assert 200 <= code <= 299
    assert message == 'OK'


@pytest.mark.asyncio
async def test_vrfy_ok(aiosmtpd_client):
    nice_address = 'test@example.com'
    await aiosmtpd_client.connect()
    code, message = await aiosmtpd_client.vrfy(nice_address)

    assert 200 <= code <= 299


@pytest.mark.asyncio
async def test_vrfy_with_blank_address(aiosmtpd_client):
    bad_address = ''
    await aiosmtpd_client.connect()
    with pytest.raises(SMTPResponseException):
        code, message = await aiosmtpd_client.vrfy(bad_address)


@pytest.mark.asyncio
async def test_expn_ok(preset_client):
    '''
    EXPN is not implemented by aiosmtpd (or anyone, really), so just fake a
    response.
    '''
    await preset_client.server.start()
    await preset_client.connect()

    preset_client.server.next_response = b'\n'.join([
        b'250-Joseph Blow <jblow@example.com>',
        b'250 Alice Smith <asmith@example.com>',
    ])
    code, message = await preset_client.expn('listserv-members')
    assert 200 <= code <= 299

    await preset_client.quit()
    await preset_client.server.stop()


@pytest.mark.asyncio
async def test_help_ok(aiosmtpd_client):
    await aiosmtpd_client.connect()
    code, message = await aiosmtpd_client.help()

    assert 200 <= code <= 299
    assert 'Supported commands' in message


@pytest.mark.asyncio
async def test_supported_methods(aiosmtpd_client):
    await aiosmtpd_client.connect()
    code, message = await aiosmtpd_client.ehlo()

    assert 200 <= code <= 299
    assert aiosmtpd_client.supports_extension('size')
    assert aiosmtpd_client.supports_extension('8bitmime')
    assert not aiosmtpd_client.supports_extension('bogus')


@pytest.mark.asyncio
async def test_sendmail_simple_success(aiosmtpd_client):
    await aiosmtpd_client.connect()
    test_address = 'test@example.com'
    mail_text = """
    Hello world!

    -a tester
    """
    errors = await aiosmtpd_client.sendmail(
        test_address, [test_address], mail_text)

    assert errors is None


@pytest.mark.asyncio
async def test_sendmail_binary_content(aiosmtpd_client):
    await aiosmtpd_client.connect()
    test_address = 'test@example.com'
    mail_text = b"""
    Hello world!

    -a tester
    """
    errors = await aiosmtpd_client.sendmail(
        test_address, [test_address], mail_text)

    assert errors is None


@pytest.mark.asyncio
async def test_sendmail_simple_failure(aiosmtpd_client):
    await aiosmtpd_client.connect()
    sender = 'test@example.com'
    recipient = '@@'
    mail_text = 'blah-blah-blah'

    with pytest.raises(SMTPRecipientsRefused):
        await aiosmtpd_client.sendmail(sender, [recipient], mail_text)


@pytest.mark.asyncio
async def test_send_message(aiosmtpd_client):
    message = email.mime.multipart.MIMEMultipart()
    message['To'] = 'test@example.com'
    message['From'] = 'test@example.com'
    message['Subject'] = 'tëst message'
    body = email.mime.text.MIMEText('''
    Hello world. UTF8 OK? 15£ ümläüts'r'us
    ''')
    message.attach(body)

    await aiosmtpd_client.connect()
    errors = await aiosmtpd_client.send_message(message)
    assert not errors


@pytest.mark.asyncio
async def test_smtp_as_context_manager(aiosmtpd_client):
    async with aiosmtpd_client:
        assert aiosmtpd_client.is_connected

        code, message = await aiosmtpd_client.noop()
        assert 200 <= code <= 299

    assert not aiosmtpd_client.is_connected

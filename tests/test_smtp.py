import asyncio
import functools
import email.mime.text
import email.mime.multipart
from email.errors import HeaderParseError

import pytest
from aiosmtpd.smtp import SMTP as BaseSMTPD
from aiosmtpd.handlers import Debugging as SMTPDDebuggingHandler
from aiosmtpd.controller import Controller

from aiosmtplib import (
    SMTP, SMTPServerDisconnected, SMTPResponseException, SMTPConnectError,
    SMTPHeloError, SMTPDataError, SMTPRecipientsRefused,
)


class SMTPD(BaseSMTPD):

    def _getaddr(self, arg):
        try:
            return super()._getaddr(arg)
        except HeaderParseError:
            return None, ''


class SMTPDController(Controller):

    def factory(self):
        return SMTPD(self.handler)


class MessageHandler(SMTPDDebuggingHandler):

    def handle_message(self, message):
        print(message)


@pytest.fixture()
def smtp_server(request):
    handler = MessageHandler()
    controller = SMTPDController(handler)
    controller.start()

    def cleanup():
        controller.stop()

    request.addfinalizer(cleanup)

    return controller


@pytest.fixture()
def smtp_client(request, smtp_server, event_loop):
    smtp_client = SMTP(
        hostname=smtp_server.hostname, port=smtp_server.port, loop=event_loop)

    return smtp_client


@pytest.mark.asyncio
async def test_helo_ok(smtp_client):
    await smtp_client.connect()
    code, message = await smtp_client.helo()

    assert 200 <= code <= 299


@pytest.mark.asyncio
async def test_ehlo_ok(smtp_client):
    await smtp_client.connect()
    code, message = await smtp_client.ehlo()

    assert 200 <= code <= 299


@pytest.mark.asyncio
async def test_rset_ok(smtp_client):
    await smtp_client.connect()
    code, message = await smtp_client.rset()

    assert 200 <= code <= 299
    assert message == 'OK'


@pytest.mark.asyncio
async def test_noop_ok(smtp_client):
    await smtp_client.connect()
    code, message = await smtp_client.noop()

    assert 200 <= code <= 299
    assert message == 'OK'


@pytest.mark.asyncio
async def test_vrfy_ok(smtp_client):
    nice_address = 'test@example.com'
    await smtp_client.connect()
    code, message = await smtp_client.vrfy(nice_address)

    assert 200 <= code <= 299


@pytest.mark.asyncio
async def test_vrfy_with_blank_address(smtp_client):
    bad_address = ''
    await smtp_client.connect()
    with pytest.raises(SMTPResponseException):
        code, message = await smtp_client.vrfy(bad_address)


@pytest.mark.skip(reason="aiosmtpd doesn't implement EXPN")
@pytest.mark.asyncio
async def test_expn_ok(smtp_client):
    await smtp_client.connect()
    code, message = await smtp_client.expn('listserv-members')

    assert 200 <= code <= 299


@pytest.mark.asyncio
async def test_help_ok(smtp_client):
    await smtp_client.connect()
    code, message = await smtp_client.help()

    assert 200 <= code <= 299
    assert 'Supported commands' in message


@pytest.mark.asyncio
async def test_supported_methods(smtp_client):
    await smtp_client.connect()
    code, message = await smtp_client.ehlo()

    assert 200 <= code <= 299
    assert smtp_client.supports_extension('size')
    assert smtp_client.supports_extension('8bitmime')
    assert not smtp_client.supports_extension('bogus')


@pytest.mark.asyncio
async def test_sendmail_simple_success(smtp_client):
    await smtp_client.connect()
    test_address = 'test@example.com'
    mail_text = """
    Hello world!

    -a tester
    """
    errors = await smtp_client.sendmail(
        test_address, [test_address], mail_text)

    assert errors is None


@pytest.mark.asyncio
async def test_sendmail_binary_content(smtp_client):
    await smtp_client.connect()
    test_address = 'test@example.com'
    mail_text = b"""
    Hello world!

    -a tester
    """
    errors = await smtp_client.sendmail(
        test_address, [test_address], mail_text)

    assert errors is None


@pytest.mark.asyncio
async def test_sendmail_simple_failure(smtp_client):
    await smtp_client.connect()
    sender = 'test@example.com'
    recipient = '@@'
    mail_text = 'blah-blah-blah'

    with pytest.raises(SMTPRecipientsRefused):
        await smtp_client.sendmail(sender, [recipient], mail_text)


@pytest.mark.asyncio
async def test_send_message(smtp_client):
    message = email.mime.multipart.MIMEMultipart()
    message['To'] = 'test@example.com'
    message['From'] = 'test@example.com'
    message['Subject'] = 'tëst message'
    body = email.mime.text.MIMEText('''
    Hello world. UTF8 OK? 15£ ümläüts'r'us
    ''')
    message.attach(body)

    await smtp_client.connect()
    errors = await smtp_client.send_message(message)
    assert not errors


@pytest.mark.asyncio
async def test_quit_then_connect_ok(smtp_client):
    await smtp_client.connect()

    code, message = await smtp_client.quit()
    assert 200 <= code <= 299

    # Next command should fail
    with pytest.raises(SMTPServerDisconnected):
        code, message = await smtp_client.noop()

    await smtp_client.connect()
    # after reconnect, it should work again
    code, message = await smtp_client.noop()
    assert 200 <= code <= 299

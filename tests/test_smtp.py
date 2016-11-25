import email.mime.text
import email.mime.multipart

import pytest

from aiosmtplib import (
    status, SMTPResponseException, SMTPRecipientsRefused, SMTPHeloError,
    SMTPDataError,
)


@pytest.mark.asyncio
async def test_helo_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.helo()

        assert response.code == status.SMTP_250_COMPLETED


@pytest.mark.asyncio
async def test_helo_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPHeloError):
            await preset_client.helo()


@pytest.mark.asyncio
async def test_ehlo_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.ehlo()

        assert response.code == status.SMTP_250_COMPLETED


@pytest.mark.asyncio
async def test_ehlo_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPHeloError):
            await preset_client.ehlo()


@pytest.mark.asyncio
async def test_ehlo_or_helo_if_needed_ehlo_success(preset_client):
    async with preset_client:
        assert preset_client.is_ehlo_or_helo_needed is True

        preset_client.server.responses.append(b'250 Ehlo is OK')
        await preset_client.ehlo_or_helo_if_needed()

        assert preset_client.is_ehlo_or_helo_needed is False


@pytest.mark.asyncio
async def test_ehlo_or_helo_if_needed_helo_success(preset_client):
    async with preset_client:
        assert preset_client.is_ehlo_or_helo_needed is True

        preset_client.server.responses.append(b'500 no ehlo')
        preset_client.server.responses.append(b'250 Helo is OK')

        await preset_client.ehlo_or_helo_if_needed()

        assert preset_client.is_ehlo_or_helo_needed is False


@pytest.mark.asyncio
async def test_ehlo_or_helo_if_needed_neither_succeeds(preset_client):
    async with preset_client:
        assert preset_client.is_ehlo_or_helo_needed is True

        preset_client.server.responses.append(b'500 no ehlo')
        preset_client.server.responses.append(b'503 no helo even!')
        with pytest.raises(SMTPHeloError):
            await preset_client.ehlo_or_helo_if_needed()


@pytest.mark.asyncio
async def test_rset_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.rset()

        assert response.code == status.SMTP_250_COMPLETED
        assert response.message == 'OK'


@pytest.mark.asyncio
async def test_rset_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.rset()


@pytest.mark.asyncio
async def test_noop_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.noop()

        assert response.code == status.SMTP_250_COMPLETED
        assert response.message == 'OK'


@pytest.mark.asyncio
async def test_noop_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.noop()


@pytest.mark.asyncio
async def test_vrfy_ok(smtpd_client):
    nice_address = 'test@example.com'
    async with smtpd_client:
        response = await smtpd_client.vrfy(nice_address)

        assert response.code == status.SMTP_252_CANNOT_VRFY


@pytest.mark.asyncio
async def test_vrfy_with_blank_address(smtpd_client):
    bad_address = ''
    async with smtpd_client:
        with pytest.raises(SMTPResponseException):
            await smtpd_client.vrfy(bad_address)


@pytest.mark.asyncio
async def test_expn_ok(preset_client):
    '''
    EXPN is not implemented by aiosmtpd (or anyone, really), so just fake a
    response.
    '''
    async with preset_client:
        preset_client.server.responses.append(b'\n'.join([
            b'250-Joseph Blow <jblow@example.com>',
            b'250 Alice Smith <asmith@example.com>',
        ]))
        response = await preset_client.expn('listserv-members')
        assert response.code == status.SMTP_250_COMPLETED


@pytest.mark.asyncio
async def test_expn_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.expn('a-list')


@pytest.mark.asyncio
async def test_rset_after_mail_error(preset_client):
    '''
    If an error response is given to the mail command, test that
    we reset the server session.
    '''
    async with preset_client:
        preset_client.server.responses.append(b'250 Hello there')
        response = await preset_client.ehlo()
        assert response.code == status.SMTP_250_COMPLETED

        preset_client.server.responses.append(b'501 bad address')
        preset_client.server.responses.append(b'250 ok')

        try:
            await preset_client.mail('>foobar<')
        except SMTPResponseException as err:
            assert err.code == 501
            assert preset_client.server.requests[-1][:4] == b'RSET'


@pytest.mark.asyncio
async def test_help_ok(smtpd_client):
    async with smtpd_client:
        help_message = await smtpd_client.help()

        assert 'Supported commands' in help_message


@pytest.mark.asyncio
async def test_help_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.help()


@pytest.mark.asyncio
async def test_quit_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.quit()


@pytest.mark.asyncio
async def test_supported_methods(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.ehlo()

        assert response.code == status.SMTP_250_COMPLETED
        assert smtpd_client.supports_extension('size')
        assert smtpd_client.supports_extension('help')
        assert not smtpd_client.supports_extension('bogus')


@pytest.mark.asyncio
async def test_mail_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        response = await smtpd_client.mail('j@example.com')

        assert response.code == status.SMTP_250_COMPLETED
        assert response.message == 'OK'


@pytest.mark.asyncio
async def test_mail_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.mail('test@example.com')


@pytest.mark.asyncio
async def test_mail_error_silent_rset_handles_disconnect(preset_client):
    async with preset_client:
        preset_client.server.goodbye = b'501 oh noes'
        with pytest.raises(SMTPResponseException):
            await preset_client.mail('test@example.com')


@pytest.mark.asyncio
async def test_rcpt_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail('j@example.com')

        response = await smtpd_client.rcpt('test@example.com')

        assert response.code == status.SMTP_250_COMPLETED
        assert response.message == 'OK'


@pytest.mark.asyncio
async def test_rcpt_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.rcpt('test@example.com')


@pytest.mark.asyncio
async def test_data_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail('j@example.com')
        await smtpd_client.rcpt('test@example.com')
        response = await smtpd_client.data(b'HELLO WORLD')

        assert response.code == status.SMTP_250_COMPLETED
        assert response.message == 'OK'


@pytest.mark.asyncio
async def test_data_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPDataError):
            await preset_client.data(b'TEST MESSAGE')


@pytest.mark.asyncio
async def test_data_complete_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'354 lets go')
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPDataError):
            await preset_client.data(b'TEST MESSAGE')


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_sendmail_simple_failure(smtpd_client):
    async with smtpd_client:
        sender = 'test@example.com'
        recipient = '@@'
        mail_text = 'blah-blah-blah'

        with pytest.raises(SMTPRecipientsRefused):
            await smtpd_client.sendmail(sender, [recipient], mail_text)


@pytest.mark.asyncio
async def test_send_message(smtpd_client):
    message = email.mime.multipart.MIMEMultipart()
    message['To'] = 'test@example.com'
    message['From'] = 'test@example.com'
    message['Subject'] = 'tëst message'
    body = email.mime.text.MIMEText('''
    Hello world. UTF8 OK? 15£ ümläüts'r'us
    ''')
    message.attach(body)

    async with smtpd_client:
        errors, message = await smtpd_client.send_message(message)

    assert not errors
    assert isinstance(errors, dict)
    assert message != ''


@pytest.mark.asyncio
async def test_gibberish_raises_exception(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'sdfjlfwqejflqw\n')
        with pytest.raises(SMTPResponseException):
            await preset_client.execute_command('NOOP')

import asyncio
import copy
import email.mime.multipart
import email.mime.text

import pytest

from aiosmtplib import (
    SMTP, SMTPDataError, SMTPHeloError, SMTPRecipientsRefused,
    SMTPResponseException, SMTPStatus, SMTPTimeoutError,
)


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_helo_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.helo()

        assert response.code == SMTPStatus.completed


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_helo_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPHeloError):
            await preset_client.helo()


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_ehlo_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.ehlo()

        assert response.code == SMTPStatus.completed


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_ehlo_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPHeloError):
            await preset_client.ehlo()


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_ehlo_or_helo_if_needed_ehlo_success(preset_client):
    async with preset_client:
        assert preset_client.is_ehlo_or_helo_needed is True

        preset_client.server.responses.append(b'250 Ehlo is OK')
        await preset_client._ehlo_or_helo_if_needed()

        assert preset_client.is_ehlo_or_helo_needed is False


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_ehlo_or_helo_if_needed_helo_success(preset_client):
    async with preset_client:
        assert preset_client.is_ehlo_or_helo_needed is True

        preset_client.server.responses.append(b'500 no ehlo')
        preset_client.server.responses.append(b'250 Helo is OK')

        await preset_client._ehlo_or_helo_if_needed()

        assert preset_client.is_ehlo_or_helo_needed is False


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_ehlo_or_helo_if_needed_neither_succeeds(preset_client):
    async with preset_client:
        assert preset_client.is_ehlo_or_helo_needed is True

        preset_client.server.responses.append(b'500 no ehlo')
        preset_client.server.responses.append(b'503 no helo even!')
        with pytest.raises(SMTPHeloError):
            await preset_client._ehlo_or_helo_if_needed()


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_rset_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.rset()

        assert response.code == SMTPStatus.completed
        assert response.message == 'OK'


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_rset_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.rset()


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_noop_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.noop()

        assert response.code == SMTPStatus.completed
        assert response.message == 'OK'


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_noop_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.noop()


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_vrfy_ok(smtpd_client):
    nice_address = 'test@example.com'
    async with smtpd_client:
        response = await smtpd_client.vrfy(nice_address)

        assert response.code == SMTPStatus.cannot_vrfy


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_vrfy_with_blank_address(smtpd_client):
    bad_address = ''
    async with smtpd_client:
        with pytest.raises(SMTPResponseException):
            await smtpd_client.vrfy(bad_address)


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_expn_ok(preset_client):
    """
    EXPN is not implemented by aiosmtpd (or anyone, really), so just fake a
    response.
    """
    async with preset_client:
        preset_client.server.responses.append(b'\n'.join([
            b'250-Joseph Blow <jblow@example.com>',
            b'250 Alice Smith <asmith@example.com>',
        ]))
        response = await preset_client.expn('listserv-members')
        assert response.code == SMTPStatus.completed


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_expn_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.expn('a-list')


@pytest.mark.asyncio(forbid_global_loop=True)
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


@pytest.mark.asyncio(forbid_global_loop=True)
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


@pytest.mark.asyncio(forbid_global_loop=True)
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


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_help_ok(smtpd_client):
    async with smtpd_client:
        help_message = await smtpd_client.help()

        assert 'Supported commands' in help_message


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_help_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.help()


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_quit_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.quit()


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_supported_methods(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.ehlo()

        assert response.code == SMTPStatus.completed
        assert smtpd_client.supports_extension('size')
        assert smtpd_client.supports_extension('help')
        assert not smtpd_client.supports_extension('bogus')


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_mail_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        response = await smtpd_client.mail('j@example.com')

        assert response.code == SMTPStatus.completed
        assert response.message == 'OK'


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_mail_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.mail('test@example.com')


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_sendmail_error_silent_rset_handles_disconnect(preset_client):
    async with preset_client:
        preset_client.server.goodbye = b'501 oh noes'
        with pytest.raises(SMTPResponseException):
            await preset_client.sendmail(
                'test@example.com', ['test2@example.com'], 'Hello World')


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_rcpt_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail('j@example.com')

        response = await smtpd_client.rcpt('test@example.com')

        assert response.code == SMTPStatus.completed
        assert response.message == 'OK'


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_rcpt_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.rcpt('test@example.com')


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_data_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail('j@example.com')
        await smtpd_client.rcpt('test@example.com')
        response = await smtpd_client.data('HELLO WORLD')

        assert response.code == SMTPStatus.completed
        assert response.message == 'OK'


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_data_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPDataError):
            await preset_client.data('TEST MESSAGE')


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_data_complete_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'354 lets go')
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPDataError):
            await preset_client.data('TEST MESSAGE')


@pytest.mark.asyncio(forbid_global_loop=True)
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


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_sendmail_multiple_times_in_sequence(smtpd_client):
    async with smtpd_client:
        sender = 'test@example.com'
        recipients = [
            'recipient1@example.com',
            'recipient2@example.com',
            'recipient3@example.com',
        ]
        mail_text = """
        Hello world!

        -a tester
        """
        for recipient in recipients:
            errors, message = await smtpd_client.sendmail(
                sender, [recipient], mail_text)

            assert not errors
            assert isinstance(errors, dict)
            assert message != ''


@pytest.mark.skip('Parallel sendmail does not work')
@pytest.mark.asyncio(forbid_global_loop=True)
async def test_sendmail_multiple_times_with_gather(smtpd_client):
    async with smtpd_client:
        sender = 'test@example.com'
        recipients = [
            'recipient1@example.com',
            'recipient2@example.com',
            'recipient3@example.com',
        ]
        mail_text = """
        Hello world!

        -a tester
        """
        tasks = [
            smtpd_client.sendmail(sender, [recipient], mail_text)
            for recipient in recipients
        ]
        results = await asyncio.gather(*tasks, loop=smtpd_client.loop)
        for errors, message in results:
            assert not errors
            assert isinstance(errors, dict)
            assert message != ''


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_multiple_clients_with_gather(smtpd_server, event_loop):
    sender = 'test@example.com'
    recipients = [
        'recipient1@example.com',
        'recipient2@example.com',
        'recipient3@example.com',
    ]
    mail_text = """
    Hello world!

    -a tester
    """

    async def connect_and_send(*args, **kwargs):
        client = SMTP(
            hostname='127.0.0.1', port=smtpd_server.port, loop=event_loop)
        async with client:
            response = await client.sendmail(*args, **kwargs)

        return response

    tasks = [
        connect_and_send(sender, [recipient], mail_text)
        for recipient in recipients
    ]
    results = await asyncio.gather(*tasks, loop=event_loop)
    for errors, message in results:
        assert not errors
        assert isinstance(errors, dict)
        assert message != ''


@pytest.mark.asyncio(forbid_global_loop=True)
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


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_sendmail_simple_failure(smtpd_client):
    async with smtpd_client:
        sender = 'test@example.com'
        recipient = '@@'
        mail_text = 'blah-blah-blah'

        with pytest.raises(SMTPRecipientsRefused):
            await smtpd_client.sendmail(sender, [recipient], mail_text)


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


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_command_timeout_error(preset_client):
    preset_client.timeout = 0.01
    async with preset_client:
        preset_client.server.responses.append(b'250 Ehlo is OK')
        preset_client.server.delay_next_response = 1
        with pytest.raises(SMTPTimeoutError):
            await preset_client.ehlo()

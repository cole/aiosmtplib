"""
Lower level SMTP command tests.
"""
import pytest

from aiosmtplib import (
    SMTPDataError, SMTPHeloError, SMTPResponseException, SMTPStatus,
    SMTPTimeoutError,
)


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_helo_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.helo()

        assert response.code == SMTPStatus.completed


async def test_helo_with_hostname(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.helo(hostname='example.com')

        assert response.code == SMTPStatus.completed


async def test_helo_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPHeloError):
            await preset_client.helo()


async def test_ehlo_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.ehlo()

        assert response.code == SMTPStatus.completed


async def test_ehlo_with_hostname(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.ehlo(hostname='example.com')

        assert response.code == SMTPStatus.completed


async def test_ehlo_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPHeloError):
            await preset_client.ehlo()


async def test_ehlo_or_helo_if_needed_ehlo_success(preset_client):
    async with preset_client:
        assert preset_client.is_ehlo_or_helo_needed is True

        preset_client.server.responses.append(b'250 Ehlo is OK')
        await preset_client._ehlo_or_helo_if_needed()

        assert preset_client.is_ehlo_or_helo_needed is False


async def test_ehlo_or_helo_if_needed_helo_success(preset_client):
    async with preset_client:
        assert preset_client.is_ehlo_or_helo_needed is True

        preset_client.server.responses.append(b'500 no ehlo')
        preset_client.server.responses.append(b'250 Helo is OK')

        await preset_client._ehlo_or_helo_if_needed()

        assert preset_client.is_ehlo_or_helo_needed is False


async def test_ehlo_or_helo_if_needed_neither_succeeds(preset_client):
    async with preset_client:
        assert preset_client.is_ehlo_or_helo_needed is True

        preset_client.server.responses.append(b'500 no ehlo')
        preset_client.server.responses.append(b'503 no helo even!')
        with pytest.raises(SMTPHeloError):
            await preset_client._ehlo_or_helo_if_needed()


async def test_ehlo_or_helo_if_needed_disconnect_on_ehlo(preset_client):
    async with preset_client:
        preset_client.server.goodbye = b'501 oh noes'
        with pytest.raises(SMTPHeloError):
            await preset_client._ehlo_or_helo_if_needed()


async def test_rset_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.rset()

        assert response.code == SMTPStatus.completed
        assert response.message == 'OK'


async def test_rset_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.rset()


async def test_noop_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.noop()

        assert response.code == SMTPStatus.completed
        assert response.message == 'OK'


async def test_noop_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.noop()


async def test_vrfy_ok(smtpd_client):
    nice_address = 'test@example.com'
    async with smtpd_client:
        response = await smtpd_client.vrfy(nice_address)

        assert response.code == SMTPStatus.cannot_vrfy


async def test_vrfy_with_blank_address(smtpd_client):
    bad_address = ''
    async with smtpd_client:
        with pytest.raises(SMTPResponseException):
            await smtpd_client.vrfy(bad_address)


async def test_expn_ok(preset_client):
    """
    EXPN is not implemented by smtpd (or anyone, really), so just fake a
    response.
    """
    async with preset_client:
        preset_client.server.responses.append(b'\n'.join([
            b'250-Joseph Blow <jblow@example.com>',
            b'250 Alice Smith <asmith@example.com>',
        ]))
        response = await preset_client.expn('listserv-members')
        assert response.code == SMTPStatus.completed


async def test_expn_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.expn('a-list')


async def test_help_ok(smtpd_client):
    async with smtpd_client:
        help_message = await smtpd_client.help()

        assert 'Supported commands' in help_message


async def test_help_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.help()


async def test_quit_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.quit()


async def test_supported_methods(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.ehlo()

        assert response.code == SMTPStatus.completed
        assert smtpd_client.supports_extension('size')
        assert smtpd_client.supports_extension('help')
        assert not smtpd_client.supports_extension('bogus')


async def test_mail_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        response = await smtpd_client.mail('j@example.com')

        assert response.code == SMTPStatus.completed
        assert response.message == 'OK'


async def test_mail_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.mail('test@example.com')


async def test_rcpt_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail('j@example.com')

        response = await smtpd_client.rcpt('test@example.com')

        assert response.code == SMTPStatus.completed
        assert response.message == 'OK'


async def test_rcpt_options(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'250 ehlo OK')
        preset_client.server.responses.append(b'250 mail OK')
        preset_client.server.responses.append(b'250 rcpt OK')

        await preset_client.ehlo()
        await preset_client.mail('j@example.com')

        response = await preset_client.rcpt(
            'test@example.com', options=['NOTIFY=FAILURE,DELAY'])

        assert response.code == SMTPStatus.completed


async def test_rcpt_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPResponseException):
            await preset_client.rcpt('test@example.com')


async def test_data_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail('j@example.com')
        await smtpd_client.rcpt('test@example.com')
        response = await smtpd_client.data('HELLO WORLD')

        assert response.code == SMTPStatus.completed
        assert response.message == 'OK'


async def test_data_with_timeout_arg(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail('j@example.com')
        await smtpd_client.rcpt('test@example.com')
        response = await smtpd_client.data('HELLO WORLD', timeout=10)

        assert response.code == SMTPStatus.completed
        assert response.message == 'OK'


async def test_data_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPDataError):
            await preset_client.data('TEST MESSAGE')


async def test_data_complete_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'354 lets go')
        preset_client.server.responses.append(b'501 oh noes')
        with pytest.raises(SMTPDataError):
            await preset_client.data('TEST MESSAGE')


async def test_command_timeout_error(preset_client):
    async with preset_client:
        # Set timeout *after connecting*, so the connection doesn't fail
        preset_client.timeout = 0.01
        preset_client.server.responses.append(b'250 Ehlo is OK')
        preset_client.server.delay_next_response = 1
        with pytest.raises(SMTPTimeoutError):
            await preset_client.ehlo()


async def test_gibberish_raises_exception(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'sdfjlfwqejflqw\n')
        with pytest.raises(SMTPResponseException):
            await preset_client.noop()

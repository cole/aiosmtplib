"""
Lower level SMTP command tests.
"""

from typing import Any

import pytest

from aiosmtplib import (
    SMTP,
    SMTPDataError,
    SMTPHeloError,
    SMTPNotSupported,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPStatus,
)

from .smtpd import (
    RecordingHandler,
    mock_response_done,
    mock_response_bad_data,
    mock_response_ehlo_full,
    mock_response_expn,
    mock_response_gibberish,
    mock_response_unavailable,
    mock_response_unrecognized_command,
    mock_response_bad_command_sequence,
    mock_response_syntax_error,
    mock_response_syntax_error_and_cleanup,
)


async def test_helo_ok(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.helo()

        assert response.code == SMTPStatus.completed


async def test_helo_with_hostname(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.helo(hostname="example.com")

        assert response.code == SMTPStatus.completed


async def test_helo_with_hostname_unset_after_connect(smtp_client: SMTP) -> None:
    async with smtp_client:
        smtp_client.local_hostname = None
        response = await smtp_client.helo()

        assert response.code == SMTPStatus.completed


@pytest.mark.smtpd_mocks(smtp_HELO=mock_response_unrecognized_command)
async def test_helo_error(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPHeloError) as exception_info:
            await smtp_client.helo()
        assert exception_info.value.code == SMTPStatus.unrecognized_command


async def test_ehlo_ok(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.ehlo()

        assert response.code == SMTPStatus.completed


async def test_ehlo_with_hostname(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.ehlo(hostname="example.com")

        assert response.code == SMTPStatus.completed


async def test_ehlo_with_hostname_unset_after_connect(smtp_client: SMTP) -> None:
    async with smtp_client:
        smtp_client.local_hostname = None
        response = await smtp_client.ehlo()

        assert response.code == SMTPStatus.completed


@pytest.mark.smtpd_mocks(smtp_EHLO=mock_response_unrecognized_command)
async def test_ehlo_error(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPHeloError) as exception_info:
            await smtp_client.ehlo()
        assert exception_info.value.code == SMTPStatus.unrecognized_command


@pytest.mark.smtpd_mocks(smtp_EHLO=mock_response_ehlo_full)
async def test_ehlo_parses_esmtp_extensions(smtp_client: SMTP) -> None:
    async with smtp_client:
        await smtp_client.ehlo()

        assert smtp_client.supports_extension("8bitmime")
        assert smtp_client.supports_extension("size")
        assert smtp_client.supports_extension("pipelining")
        assert smtp_client.supports_extension("ENHANCEDSTATUSCODES")
        assert not smtp_client.supports_extension("notreal")


@pytest.mark.smtpd_mocks(smtp_EHLO=mock_response_done)
async def test_ehlo_with_no_extensions(smtp_client: SMTP) -> None:
    async with smtp_client:
        await smtp_client.ehlo()

        assert not smtp_client.supports_extension("size")


async def test_ehlo_or_helo_if_needed_ehlo_success(smtp_client: SMTP) -> None:
    async with smtp_client:
        assert smtp_client.is_ehlo_or_helo_needed is True

        await smtp_client._ehlo_or_helo_if_needed()

        assert smtp_client.is_ehlo_or_helo_needed is False


@pytest.mark.smtpd_mocks(smtp_EHLO=mock_response_unrecognized_command)
async def test_ehlo_or_helo_if_needed_helo_success(smtp_client: SMTP) -> None:
    async with smtp_client:
        assert smtp_client.is_ehlo_or_helo_needed is True

        await smtp_client._ehlo_or_helo_if_needed()

        assert smtp_client.is_ehlo_or_helo_needed is False


@pytest.mark.smtpd_mocks(
    smtp_HELO=mock_response_unrecognized_command,
    smtp_EHLO=mock_response_unrecognized_command,
)
async def test_ehlo_or_helo_if_needed_neither_succeeds(smtp_client: SMTP) -> None:
    async with smtp_client:
        assert smtp_client.is_ehlo_or_helo_needed is True

        with pytest.raises(SMTPHeloError) as exception_info:
            await smtp_client._ehlo_or_helo_if_needed()
        assert exception_info.value.code == SMTPStatus.unrecognized_command


@pytest.mark.smtpd_mocks(smtp_EHLO=mock_response_unavailable)
async def test_ehlo_or_helo_if_needed_disconnect_after_ehlo(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPHeloError):
            await smtp_client._ehlo_or_helo_if_needed()


async def test_rset_ok(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.rset()

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


@pytest.mark.smtpd_mocks(smtp_RSET=mock_response_bad_command_sequence)
async def test_rset_error(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.rset()
        assert exception_info.value.code == SMTPStatus.bad_command_sequence


async def test_noop_ok(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.noop()

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


@pytest.mark.smtpd_mocks(smtp_NOOP=mock_response_syntax_error)
async def test_noop_error(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.noop()
        assert exception_info.value.code == SMTPStatus.syntax_error


async def test_vrfy_ok(smtp_client: SMTP) -> None:
    nice_address = "test@example.com"
    async with smtp_client:
        response = await smtp_client.vrfy(nice_address)

        assert response.code == SMTPStatus.cannot_vrfy


async def test_vrfy_with_blank_address(smtp_client: SMTP) -> None:
    bad_address = ""
    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.vrfy(bad_address)


@pytest.mark.smtpd_options(smtputf8=True)
async def test_vrfy_smtputf8_supported(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.vrfy("tést@exåmple.com", options=["SMTPUTF8"])

        assert response.code == SMTPStatus.cannot_vrfy


@pytest.mark.smtpd_options(smtputf8=False)
async def test_vrfy_smtputf8_not_supported(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPNotSupported):
            await smtp_client.vrfy("tést@exåmple.com", options=["SMTPUTF8"])


@pytest.mark.smtpd_mocks(smtp_EXPN=mock_response_expn)
async def test_expn_ok(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.expn("listserv-members")
        assert response.code == SMTPStatus.completed


async def test_expn_error(smtp_client: SMTP) -> None:
    """
    Since EXPN isn't implemented by aiosmtpd, it raises an exception by default.
    """
    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.expn("a-list")


@pytest.mark.smtpd_options(smtputf8=True)
@pytest.mark.smtpd_mocks(smtp_EXPN=mock_response_expn)
async def test_expn_smtputf8_supported(smtp_client: SMTP) -> None:
    utf8_list = "tést-lïst"
    async with smtp_client:
        response = await smtp_client.expn(utf8_list, options=["SMTPUTF8"])

        assert response.code == SMTPStatus.completed


@pytest.mark.smtpd_options(smtputf8=False)
async def test_expn_smtputf8_not_supported(smtp_client: SMTP) -> None:
    utf8_list = "tést-lïst"
    async with smtp_client:
        with pytest.raises(SMTPNotSupported):
            await smtp_client.expn(utf8_list, options=["SMTPUTF8"])


async def test_help_ok(smtp_client: SMTP) -> None:
    async with smtp_client:
        help_message = await smtp_client.help()

        assert "Supported commands" in help_message


@pytest.mark.smtpd_mocks(smtp_HELP=mock_response_syntax_error)
async def test_help_error(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.help()
        assert exception_info.value.code == SMTPStatus.syntax_error


@pytest.mark.smtpd_mocks(smtp_QUIT=mock_response_syntax_error_and_cleanup)
async def test_quit_error(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.quit()
        assert exception_info.value.code == SMTPStatus.syntax_error


async def test_supported_methods(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.ehlo()

        assert response.code == SMTPStatus.completed
        assert smtp_client.supports_extension("size")
        assert smtp_client.supports_extension("help")
        assert not smtp_client.supports_extension("bogus")


async def test_mail_ok(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.mail("j@example.com")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


@pytest.mark.smtpd_mocks(smtp_MAIL=mock_response_bad_command_sequence)
async def test_mail_error(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.mail("test@example.com")
        assert exception_info.value.code == SMTPStatus.bad_command_sequence


async def test_mail_options_not_implemented(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.mail("j@example.com", options=["OPT=1"])


@pytest.mark.smtpd_options(smtputf8=True)
async def test_mail_smtputf8(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.mail(
            "tést@exåmple.com", options=["SMTPUTF8"], encoding="utf-8"
        )

        assert response.code == SMTPStatus.completed


async def test_mail_default_encoding_utf8_encode_error(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(UnicodeEncodeError):
            await smtp_client.mail("tést@exåmple.com", options=["SMTPUTF8"])


async def test_rcpt_ok(smtp_client: SMTP) -> None:
    async with smtp_client:
        await smtp_client.mail("j@example.com")

        response = await smtp_client.rcpt("test@example.com")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


@pytest.mark.smtpd_mocks(smtp_RCPT=mock_response_done)
async def test_rcpt_options_ok(smtp_client: SMTP) -> None:
    async with smtp_client:
        await smtp_client.mail("j@example.com")

        response = await smtp_client.rcpt(
            "test@example.com", options=["NOTIFY=FAILURE,DELAY"]
        )

        assert response.code == SMTPStatus.completed


async def test_rcpt_options_not_implemented(smtp_client: SMTP) -> None:
    # RCPT options are not implemented in aiosmtpd, so any option will return 555
    async with smtp_client:
        await smtp_client.mail("j@example.com")

        with pytest.raises(SMTPResponseException) as err:
            await smtp_client.rcpt("test@example.com", options=["OPT=1"])
            assert err.value.code == SMTPStatus.syntax_error


@pytest.mark.smtpd_mocks(smtp_RCPT=mock_response_syntax_error)
async def test_rcpt_error(smtp_client: SMTP) -> None:
    async with smtp_client:
        await smtp_client.mail("j@example.com")

        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.rcpt("test@example.com")
        assert exception_info.value.code == SMTPStatus.syntax_error


@pytest.mark.smtpd_options(smtputf8=True)
async def test_rcpt_smtputf8(smtp_client: SMTP) -> None:
    async with smtp_client:
        await smtp_client.mail("j@example.com", options=["SMTPUTF8"])
        response = await smtp_client.rcpt("tést@exåmple.com", encoding="utf-8")

        assert response.code == SMTPStatus.completed


async def test_rcpt_default_encoding_utf8_encode_error(smtp_client: SMTP) -> None:
    async with smtp_client:
        await smtp_client.mail("j@example.com")

        with pytest.raises(UnicodeEncodeError):
            await smtp_client.rcpt("tést@exåmple.com", options=["SMTPUTF8"])


async def test_data_ok(smtp_client: SMTP) -> None:
    async with smtp_client:
        await smtp_client.mail("j@example.com")
        await smtp_client.rcpt("test@example.com")
        response = await smtp_client.data("HELLO WORLD")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


@pytest.mark.smtpd_mocks(smtp_DATA=mock_response_bad_command_sequence)
async def test_data_error_on_start_input(smtp_client: SMTP) -> None:
    async with smtp_client:
        await smtp_client.mail("admin@example.com")
        await smtp_client.rcpt("test@example.com")
        with pytest.raises(SMTPDataError) as exception_info:
            await smtp_client.data("TEST MESSAGE")
        assert exception_info.value.code == SMTPStatus.bad_command_sequence


async def test_data_complete_error(
    smtp_client: SMTP,
    smtpd_handler: RecordingHandler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_handler, "handle_DATA", mock_response_syntax_error)

    async with smtp_client:
        await smtp_client.mail("admin@example.com")
        await smtp_client.rcpt("test@example.com")
        with pytest.raises(SMTPDataError) as exception_info:
            await smtp_client.data("TEST MESSAGE")
        assert exception_info.value.code == SMTPStatus.syntax_error


async def test_data_error_when_disconnected() -> None:
    client = SMTP()

    with pytest.raises(SMTPServerDisconnected):
        await client.data("HELLO WORLD")


@pytest.mark.smtpd_mocks(smtp_NOOP=mock_response_gibberish)
async def test_gibberish_raises_exception(smtp_client: SMTP) -> None:
    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.noop()


@pytest.mark.smtpd_mocks(smtp_NOOP=mock_response_bad_data)
async def test_badly_encoded_text_response(smtp_client: SMTP) -> None:
    async with smtp_client:
        response = await smtp_client.noop()

    assert response.code == SMTPStatus.completed


async def test_header_injection(
    smtp_client: SMTP,
    received_commands: list[tuple[str, tuple[Any, ...]]],
) -> None:
    async with smtp_client:
        await smtp_client.mail("test@example.com\r\nX-Malicious-Header: bad stuff")

    assert len(received_commands) > 0
    for command in received_commands:
        for arg in command:
            assert "bad stuff" not in arg

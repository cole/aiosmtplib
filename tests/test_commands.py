"""
Lower level SMTP command tests.
"""
import pytest

from aiosmtplib import (
    SMTPDataError,
    SMTPHeloError,
    SMTPNotSupported,
    SMTPResponseException,
    SMTPStatus,
)


pytestmark = pytest.mark.asyncio()


@pytest.fixture(scope="session")
def bad_data_response_handler(request):
    async def bad_data_response(smtpd, *args, **kwargs):
        smtpd._writer.write(b"250 \xFF\xFF\xFF\xFF\r\n")
        await smtpd._writer.drain()

    return bad_data_response


async def test_helo_ok(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.helo()

        assert response.code == SMTPStatus.completed


async def test_helo_with_hostname(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.helo(hostname="example.com")

        assert response.code == SMTPStatus.completed


async def test_helo_error(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
):
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_class, "smtp_HELO", response_handler)

    async with smtp_client:
        with pytest.raises(SMTPHeloError) as exception_info:
            await smtp_client.helo()
        assert exception_info.value.code == error_code


async def test_ehlo_ok(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.ehlo()

        assert response.code == SMTPStatus.completed


async def test_ehlo_with_hostname(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.ehlo(hostname="example.com")

        assert response.code == SMTPStatus.completed


async def test_ehlo_error(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
):
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_class, "smtp_EHLO", response_handler)

    async with smtp_client:
        with pytest.raises(SMTPHeloError) as exception_info:
            await smtp_client.ehlo()
        assert exception_info.value.code == error_code


async def test_ehlo_parses_esmtp_extensions(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    ehlo_response = """250-localhost
250-PIPELINING
250-8BITMIME
250-SIZE 512000
250-DSN
250-ENHANCEDSTATUSCODES
250-EXPN
250-HELP
250-SAML
250-SEND
250-SOML
250-TURN
250-XADR
250-XSTA
250-ETRN
250 XGEN"""
    monkeypatch.setattr(
        smtpd_class, "smtp_EHLO", smtpd_response_handler_factory(ehlo_response)
    )

    async with smtp_client:
        await smtp_client.ehlo()

        assert smtp_client.supports_extension("8bitmime")
        assert smtp_client.supports_extension("size")
        assert smtp_client.supports_extension("pipelining")
        assert smtp_client.supports_extension("ENHANCEDSTATUSCODES")
        assert not smtp_client.supports_extension("notreal")


async def test_ehlo_with_no_extensions(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    response_handler = smtpd_response_handler_factory(
        "{} all done".format(SMTPStatus.completed)
    )
    monkeypatch.setattr(smtpd_class, "smtp_EHLO", response_handler)

    async with smtp_client:
        await smtp_client.ehlo()

        assert not smtp_client.supports_extension("size")


async def test_ehlo_or_helo_if_needed_ehlo_success(smtp_client, smtpd_server):
    async with smtp_client:
        assert smtp_client.is_ehlo_or_helo_needed is True

        await smtp_client._ehlo_or_helo_if_needed()

        assert smtp_client.is_ehlo_or_helo_needed is False


async def test_ehlo_or_helo_if_needed_helo_success(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
):
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_class, "smtp_EHLO", response_handler)

    async with smtp_client:
        assert smtp_client.is_ehlo_or_helo_needed is True

        await smtp_client._ehlo_or_helo_if_needed()

        assert smtp_client.is_ehlo_or_helo_needed is False


@pytest.mark.parametrize(
    "ehlo_error_code",
    [
        SMTPStatus.mailbox_unavailable,
        SMTPStatus.unrecognized_command,
        SMTPStatus.bad_command_sequence,
        SMTPStatus.syntax_error,
    ],
    ids=[
        SMTPStatus.mailbox_unavailable.name,
        SMTPStatus.unrecognized_command.name,
        SMTPStatus.bad_command_sequence.name,
        SMTPStatus.syntax_error.name,
    ],
)
async def test_ehlo_or_helo_if_needed_neither_succeeds(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
    ehlo_error_code,
):
    helo_response_handler = smtpd_response_handler_factory(
        "{} error".format(error_code)
    )
    monkeypatch.setattr(smtpd_class, "smtp_HELO", helo_response_handler)

    ehlo_response_handler = smtpd_response_handler_factory(
        "{} error".format(ehlo_error_code)
    )
    monkeypatch.setattr(smtpd_class, "smtp_EHLO", ehlo_response_handler)

    async with smtp_client:
        assert smtp_client.is_ehlo_or_helo_needed is True

        with pytest.raises(SMTPHeloError) as exception_info:
            await smtp_client._ehlo_or_helo_if_needed()
        assert exception_info.value.code == error_code


async def test_ehlo_or_helo_if_needed_disconnect_after_ehlo(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    response_handler = smtpd_response_handler_factory(
        "{} retry in 5 minutes".format(SMTPStatus.domain_unavailable), close_after=True
    )
    monkeypatch.setattr(smtpd_class, "smtp_EHLO", response_handler)

    async with smtp_client:
        with pytest.raises(SMTPHeloError):
            await smtp_client._ehlo_or_helo_if_needed()


async def test_rset_ok(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.rset()

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_rset_error(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
):
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_class, "smtp_RSET", response_handler)

    async with smtp_client:
        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.rset()
        assert exception_info.value.code == error_code


async def test_noop_ok(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.noop()

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_noop_error(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
):
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", response_handler)

    async with smtp_client:
        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.noop()
        assert exception_info.value.code == error_code


async def test_vrfy_ok(smtp_client, smtpd_server):
    nice_address = "test@example.com"
    async with smtp_client:
        response = await smtp_client.vrfy(nice_address)

        assert response.code == SMTPStatus.cannot_vrfy


async def test_vrfy_with_blank_address(smtp_client, smtpd_server):
    bad_address = ""
    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.vrfy(bad_address)


async def test_vrfy_smtputf8_supported(smtp_client_smtputf8, smtpd_server_smtputf8):
    async with smtp_client_smtputf8:
        response = await smtp_client_smtputf8.vrfy(
            "tést@exåmple.com", options=["SMTPUTF8"]
        )

        assert response.code == SMTPStatus.cannot_vrfy


async def test_vrfy_smtputf8_not_supported(smtp_client, smtpd_server):
    async with smtp_client:
        with pytest.raises(SMTPNotSupported):
            await smtp_client.vrfy("tést@exåmple.com", options=["SMTPUTF8"])


async def test_expn_ok(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    response_handler = smtpd_response_handler_factory(
        """250-Joseph Blow <jblow@example.com>
250 Alice Smith <asmith@example.com>"""
    )
    monkeypatch.setattr(smtpd_class, "smtp_EXPN", response_handler)

    async with smtp_client:
        response = await smtp_client.expn("listserv-members")
        assert response.code == SMTPStatus.completed


async def test_expn_error(smtp_client, smtpd_server):
    """
    Since EXPN isn't implemented by aiosmtpd, it raises an exception by default.
    """
    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.expn("a-list")


async def test_expn_smtputf8_supported(
    smtp_client_smtputf8,
    smtpd_server_smtputf8,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
):
    response_handler = smtpd_response_handler_factory(
        """250-Joseph Blow <jblow@example.com>
250 Alice Smith <asmith@example.com>"""
    )
    monkeypatch.setattr(smtpd_class, "smtp_EXPN", response_handler)

    utf8_list = "tést-lïst"
    async with smtp_client_smtputf8:
        response = await smtp_client_smtputf8.expn(utf8_list, options=["SMTPUTF8"])

        assert response.code == SMTPStatus.completed


async def test_expn_smtputf8_not_supported(smtp_client, smtpd_server):
    utf8_list = "tést-lïst"
    async with smtp_client:
        with pytest.raises(SMTPNotSupported):
            await smtp_client.expn(utf8_list, options=["SMTPUTF8"])


async def test_help_ok(smtp_client, smtpd_server):
    async with smtp_client:
        help_message = await smtp_client.help()

        assert "Supported commands" in help_message


async def test_help_error(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
):
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_class, "smtp_HELP", response_handler)

    async with smtp_client:
        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.help()
        assert exception_info.value.code == error_code


async def test_quit_error(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
):
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_class, "smtp_QUIT", response_handler)

    async with smtp_client:
        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.quit()
        assert exception_info.value.code == error_code


async def test_supported_methods(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.ehlo()

        assert response.code == SMTPStatus.completed
        assert smtp_client.supports_extension("size")
        assert smtp_client.supports_extension("help")
        assert not smtp_client.supports_extension("bogus")


async def test_mail_ok(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.mail("j@example.com")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_mail_error(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
):
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_class, "smtp_MAIL", response_handler)

    async with smtp_client:
        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.mail("test@example.com")
        assert exception_info.value.code == error_code


async def test_mail_options_not_implemented(smtp_client, smtpd_server):
    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.mail("j@example.com", options=["OPT=1"])


async def test_mail_smtputf8(smtp_client_smtputf8, smtpd_server_smtputf8):
    async with smtp_client_smtputf8:
        response = await smtp_client_smtputf8.mail(
            "tést@exåmple.com", options=["SMTPUTF8"], encoding="utf-8"
        )

        assert response.code == SMTPStatus.completed


async def test_mail_default_encoding_utf8_encode_error(smtp_client, smtpd_server):
    async with smtp_client:
        with pytest.raises(UnicodeEncodeError):
            await smtp_client.mail("tést@exåmple.com", options=["SMTPUTF8"])


async def test_rcpt_ok(smtp_client, smtpd_server):
    async with smtp_client:
        await smtp_client.mail("j@example.com")

        response = await smtp_client.rcpt("test@example.com")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_rcpt_options_ok(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    # RCPT options are not implemented in aiosmtpd, so force success response
    response_handler = smtpd_response_handler_factory(
        "{} all done".format(SMTPStatus.completed)
    )
    monkeypatch.setattr(smtpd_class, "smtp_RCPT", response_handler)

    async with smtp_client:
        await smtp_client.mail("j@example.com")

        response = await smtp_client.rcpt(
            "test@example.com", options=["NOTIFY=FAILURE,DELAY"]
        )

        assert response.code == SMTPStatus.completed


async def test_rcpt_options_not_implemented(smtp_client, smtpd_server):
    # RCPT options are not implemented in aiosmtpd, so any option will return 555
    async with smtp_client:
        await smtp_client.mail("j@example.com")

        with pytest.raises(SMTPResponseException) as err:
            await smtp_client.rcpt("test@example.com", options=["OPT=1"])
            assert err.code == SMTPStatus.syntax_error


async def test_rcpt_error(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
):
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_class, "smtp_RCPT", response_handler)

    async with smtp_client:
        await smtp_client.mail("j@example.com")

        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.rcpt("test@example.com")
        assert exception_info.value.code == error_code


async def test_rcpt_smtputf8(smtp_client_smtputf8, smtpd_server_smtputf8):
    async with smtp_client_smtputf8:
        await smtp_client_smtputf8.mail("j@example.com", options=["SMTPUTF8"])
        response = await smtp_client_smtputf8.rcpt("tést@exåmple.com", encoding="utf-8")

        assert response.code == SMTPStatus.completed


async def test_rcpt_default_encoding_utf8_encode_error(smtp_client, smtpd_server):
    async with smtp_client:
        await smtp_client.mail("j@example.com")

        with pytest.raises(UnicodeEncodeError):
            await smtp_client.rcpt("tést@exåmple.com", options=["SMTPUTF8"])


async def test_data_ok(smtp_client, smtpd_server):
    async with smtp_client:
        await smtp_client.mail("j@example.com")
        await smtp_client.rcpt("test@example.com")
        response = await smtp_client.data("HELLO WORLD")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_data_error_on_start_input(
    smtp_client,
    smtpd_server,
    smtpd_class,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
):
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_class, "smtp_DATA", response_handler)

    async with smtp_client:
        await smtp_client.mail("admin@example.com")
        await smtp_client.rcpt("test@example.com")
        with pytest.raises(SMTPDataError) as exception_info:
            await smtp_client.data("TEST MESSAGE")
        assert exception_info.value.code == error_code


async def test_data_complete_error(
    smtp_client,
    smtpd_server,
    smtpd_handler,
    smtpd_response_handler_factory,
    monkeypatch,
    error_code,
):
    response_handler = smtpd_response_handler_factory("{} error".format(error_code))
    monkeypatch.setattr(smtpd_handler, "handle_DATA", response_handler)

    async with smtp_client:
        await smtp_client.mail("admin@example.com")
        await smtp_client.rcpt("test@example.com")
        with pytest.raises(SMTPDataError) as exception_info:
            await smtp_client.data("TEST MESSAGE")
        assert exception_info.value.code == error_code


async def test_gibberish_raises_exception(
    smtp_client, smtpd_server, smtpd_class, smtpd_response_handler_factory, monkeypatch
):
    response_handler = smtpd_response_handler_factory("sdfjlfwqejflqw")
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", response_handler)

    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.noop()


async def test_badly_encoded_text_response(
    smtp_client, smtpd_server, smtpd_class, bad_data_response_handler, monkeypatch
):
    monkeypatch.setattr(smtpd_class, "smtp_NOOP", bad_data_response_handler)

    async with smtp_client:
        response = await smtp_client.noop()

    assert response.code == SMTPStatus.completed


async def test_header_injection(smtp_client, smtpd_server, received_commands):
    async with smtp_client:
        await smtp_client.mail("test@example.com\r\nX-Malicious-Header: bad stuff")

    assert len(received_commands) > 0
    for command in received_commands:
        for arg in command:
            assert "bad stuff" not in arg

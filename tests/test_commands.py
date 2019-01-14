"""
Lower level SMTP command tests.
"""
import pytest

from aiosmtplib import SMTPDataError, SMTPHeloError, SMTPResponseException, SMTPStatus


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_helo_ok(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.helo()

        assert response.code == SMTPStatus.completed


async def test_helo_with_hostname(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.helo(hostname="example.com")

        assert response.code == SMTPStatus.completed


async def test_helo_error(smtp_client, smtpd_server, smtpd_handler, monkeypatch):
    monkeypatch.setattr(smtpd_handler, "HELO_response_message", "501 oh noes")

    async with smtp_client:
        with pytest.raises(SMTPHeloError):
            await smtp_client.helo()


async def test_ehlo_ok(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.ehlo()

        assert response.code == SMTPStatus.completed


async def test_ehlo_with_hostname(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.ehlo(hostname="example.com")

        assert response.code == SMTPStatus.completed


async def test_ehlo_error(smtp_client, smtpd_server, smtpd_handler, monkeypatch):
    monkeypatch.setattr(smtpd_handler, "EHLO_response_message", "501 oh noes")

    async with smtp_client:
        with pytest.raises(SMTPHeloError):
            await smtp_client.ehlo()


async def test_ehlo_parses_esmtp_extensions(
    smtp_client, smtpd_server, smtpd_handler, monkeypatch
):
    ehlo_response = """250-PIPELINING
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
    monkeypatch.setattr(smtpd_handler, "EHLO_response_message", ehlo_response)

    async with smtp_client:
        await smtp_client.ehlo()

        # 8BITMIME and SIZE are supported by default in aiosmtpd.
        assert smtp_client.supports_extension("8bitmime")
        assert smtp_client.supports_extension("size")

        assert smtp_client.supports_extension("pipelining")
        assert smtp_client.supports_extension("ENHANCEDSTATUSCODES")
        assert not smtp_client.supports_extension("notreal")


async def test_ehlo_with_no_extensions(
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    async def ehlo_response(self, hostname):
        await self.push("250 all good")

    monkeypatch.setattr(smtpd_class, "smtp_EHLO", ehlo_response)

    async with smtp_client:
        await smtp_client.ehlo()

        assert not smtp_client.supports_extension("size")


async def test_ehlo_or_helo_if_needed_ehlo_success(smtp_client, smtpd_server):
    async with smtp_client:
        assert smtp_client.is_ehlo_or_helo_needed is True

        await smtp_client._ehlo_or_helo_if_needed()

        assert smtp_client.is_ehlo_or_helo_needed is False


async def test_ehlo_or_helo_if_needed_helo_success(
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    async def ehlo_response(self, hostname):
        await self.push("500 no ehlo")

    monkeypatch.setattr(smtpd_class, "smtp_EHLO", ehlo_response)

    async with smtp_client:
        assert smtp_client.is_ehlo_or_helo_needed is True

        await smtp_client._ehlo_or_helo_if_needed()

        assert smtp_client.is_ehlo_or_helo_needed is False


async def test_ehlo_or_helo_if_needed_neither_succeeds(
    smtp_client, smtpd_server, smtpd_class, smtpd_handler, monkeypatch
):
    monkeypatch.setattr(smtpd_handler, "HELO_response_message", "500 no helo")

    async def ehlo_response(self, hostname):
        await self.push("500 no ehlo")

    monkeypatch.setattr(smtpd_class, "smtp_EHLO", ehlo_response)

    async with smtp_client:
        assert smtp_client.is_ehlo_or_helo_needed is True

        with pytest.raises(SMTPHeloError):
            await smtp_client._ehlo_or_helo_if_needed()


async def test_ehlo_or_helo_if_needed_disconnect_after_ehlo(
    smtp_client, smtpd_server, smtpd_class, monkeypatch, event_loop
):
    async def ehlo_response(self, hostname):
        await self.push("421 bye for now")
        self.transport.close()

    monkeypatch.setattr(smtpd_class, "smtp_EHLO", ehlo_response)

    async with smtp_client:
        with pytest.raises(SMTPHeloError):
            await smtp_client._ehlo_or_helo_if_needed()


async def test_rset_ok(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.rset()

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_rset_error(smtp_client, smtpd_server, smtpd_handler, monkeypatch):
    monkeypatch.setattr(smtpd_handler, "RSET_response_message", "501 oh noes")

    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.rset()


async def test_noop_ok(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.noop()

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_noop_error(smtp_client, smtpd_server, smtpd_handler, monkeypatch):
    monkeypatch.setattr(smtpd_handler, "NOOP_response_message", "501 oh noes")

    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.noop()


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


async def test_expn_ok(smtp_client, smtpd_server, smtpd_handler, monkeypatch):
    expn_response = """250-Joseph Blow <jblow@example.com>
250 Alice Smith <asmith@example.com>"""
    monkeypatch.setattr(smtpd_handler, "EXPN_response_message", expn_response)

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


async def test_help_ok(smtp_client, smtpd_server):
    async with smtp_client:
        help_message = await smtp_client.help()

        assert "Supported commands" in help_message


async def test_help_error(smtp_client, smtpd_server, smtpd_handler, monkeypatch):
    monkeypatch.setattr(smtpd_handler, "HELP_response_message", "501 error")

    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.help()


async def test_quit_error(smtp_client, smtpd_server, smtpd_handler, monkeypatch):
    monkeypatch.setattr(smtpd_handler, "QUIT_response_message", "501 error")

    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.quit()


async def test_supported_methods(smtp_client, smtpd_server):
    async with smtp_client:
        response = await smtp_client.ehlo()

        assert response.code == SMTPStatus.completed
        assert smtp_client.supports_extension("size")
        assert smtp_client.supports_extension("help")
        assert not smtp_client.supports_extension("bogus")


async def test_mail_ok(smtp_client, smtpd_server):
    async with smtp_client:
        await smtp_client.ehlo()
        response = await smtp_client.mail("j@example.com")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_mail_error(smtp_client, smtpd_server, smtpd_handler, monkeypatch):
    monkeypatch.setattr(smtpd_handler, "MAIL_response_message", "501 error")

    async with smtp_client:
        await smtp_client.ehlo()

        with pytest.raises(SMTPResponseException):
            await smtp_client.mail("test@example.com")


async def test_rcpt_ok(smtp_client, smtpd_server):
    async with smtp_client:
        await smtp_client.ehlo()
        await smtp_client.mail("j@example.com")

        response = await smtp_client.rcpt("test@example.com")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_rcpt_options_ok(smtp_client, smtpd_server, smtpd_class, monkeypatch):
    # RCPT options are not implemented in aiosmtpd, so force success response
    async def rcpt_response(self, arg):
        await self.push("250 rcpt ok")

    monkeypatch.setattr(smtpd_class, "smtp_RCPT", rcpt_response)

    async with smtp_client:
        await smtp_client.ehlo()
        await smtp_client.mail("j@example.com")

        response = await smtp_client.rcpt(
            "test@example.com", options=["NOTIFY=FAILURE,DELAY"]
        )

        assert response.code == SMTPStatus.completed


async def test_rcpt_options_not_implemented(smtp_client, smtpd_server):
    # RCPT options are not implemented in aiosmtpd, so any option will return 555
    async with smtp_client:
        await smtp_client.ehlo()
        await smtp_client.mail("j@example.com")

        with pytest.raises(SMTPResponseException) as err:
            await smtp_client.rcpt("test@example.com", options=["OPT=1"])
            assert err.code == SMTPStatus.syntax_error


async def test_rcpt_error(smtp_client, smtpd_server, smtpd_handler, monkeypatch):
    monkeypatch.setattr(smtpd_handler, "RCPT_response_message", "501 error")

    async with smtp_client:
        await smtp_client.ehlo()
        await smtp_client.mail("j@example.com")

        with pytest.raises(SMTPResponseException):
            await smtp_client.rcpt("test@example.com")


async def test_data_ok(smtp_client, smtpd_server):
    async with smtp_client:
        await smtp_client.ehlo()
        await smtp_client.mail("j@example.com")
        await smtp_client.rcpt("test@example.com")
        response = await smtp_client.data("HELLO WORLD")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_data_error_on_start_input(
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    async def data_response(self, arg):
        await self.push("501 error")

    monkeypatch.setattr(smtpd_class, "smtp_DATA", data_response)

    async with smtp_client:
        await smtp_client.ehlo()
        await smtp_client.mail("admin@example.com")
        await smtp_client.rcpt("test@example.com")
        with pytest.raises(SMTPDataError):
            await smtp_client.data("TEST MESSAGE")


async def test_data_complete_error(
    smtp_client, smtpd_server, smtpd_handler, monkeypatch
):
    monkeypatch.setattr(smtpd_handler, "DATA_response_message", "501 error")

    async with smtp_client:
        await smtp_client.ehlo()
        await smtp_client.mail("admin@example.com")
        await smtp_client.rcpt("test@example.com")
        with pytest.raises(SMTPDataError):
            await smtp_client.data("TEST MESSAGE")


async def test_gibberish_raises_exception(
    smtp_client, smtpd_server, smtpd_handler, monkeypatch
):
    monkeypatch.setattr(smtpd_handler, "NOOP_response_message", "sdfjlfwqejflqw")

    async with smtp_client:
        with pytest.raises(SMTPResponseException):
            await smtp_client.noop()


async def test_badly_encoded_text_response(
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    async def noop_response(self, arg):
        self._writer.write(b"250 \xFF\xFF\xFF\xFF\r\n")
        await self._writer.drain()

    monkeypatch.setattr(smtpd_class, "smtp_NOOP", noop_response)

    async with smtp_client:
        response = await smtp_client.noop()

    assert response.code == SMTPStatus.completed

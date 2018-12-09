"""
Lower level SMTP command tests.
"""
import asyncio

import pytest

from aiosmtplib import (
    SMTPDataError,
    SMTPHeloError,
    SMTPResponseException,
    SMTPStatus,
    SMTPTimeoutError,
)


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_helo_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.helo()

        assert response.code == SMTPStatus.completed


async def test_helo_with_hostname(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.helo(hostname="example.com")

        assert response.code == SMTPStatus.completed


async def test_helo_error(smtpd_client, smtpd_handler, monkeypatch):
    async def helo_response(self, session, envelope, hostname):
        return "501 oh noes"

    monkeypatch.setattr(smtpd_handler, "handle_HELO", helo_response, raising=False)

    async with smtpd_client:
        with pytest.raises(SMTPHeloError):
            await smtpd_client.helo()


async def test_ehlo_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.ehlo()

        assert response.code == SMTPStatus.completed


async def test_ehlo_with_hostname(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.ehlo(hostname="example.com")

        assert response.code == SMTPStatus.completed


async def test_ehlo_error(smtpd_client, smtpd_handler, monkeypatch):
    async def ehlo_response(self, session, envelope, hostname):
        return "501 oh noes"

    monkeypatch.setattr(smtpd_handler, "handle_EHLO", ehlo_response, raising=False)

    async with smtpd_client:
        with pytest.raises(SMTPHeloError):
            await smtpd_client.ehlo()


async def test_ehlo_parses_esmtp_extensions(smtpd_client, smtpd_handler, monkeypatch):
    async def ehlo_response(self, session, envelope, hostname):
        return """250-PIPELINING
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

    monkeypatch.setattr(smtpd_handler, "handle_EHLO", ehlo_response, raising=False)

    async with smtpd_client:
        await smtpd_client.ehlo()

        # 8BITMIME and SIZE are supported by default in aiosmtpd.
        assert smtpd_client.supports_extension("8bitmime")
        assert smtpd_client.supports_extension("size")

        assert smtpd_client.supports_extension("pipelining")
        assert smtpd_client.supports_extension("ENHANCEDSTATUSCODES")
        assert not smtpd_client.supports_extension("notreal")


async def test_ehlo_with_no_extensions(smtpd_client, aiosmtpd_class, monkeypatch):
    async def ehlo_response(self, hostname):
        await self.push("250 all good")

    monkeypatch.setattr(aiosmtpd_class, "smtp_EHLO", ehlo_response, raising=False)

    async with smtpd_client:
        await smtpd_client.ehlo()

        assert not smtpd_client.supports_extension("size")


async def test_ehlo_or_helo_if_needed_ehlo_success(smtpd_client):
    async with smtpd_client:
        assert smtpd_client.is_ehlo_or_helo_needed is True

        await smtpd_client._ehlo_or_helo_if_needed()

        assert smtpd_client.is_ehlo_or_helo_needed is False


async def test_ehlo_or_helo_if_needed_helo_success(
    smtpd_client, smtpd_handler, monkeypatch
):
    async def ehlo_response(self, session, envelope, hostname):
        return "500 no bueno"

    monkeypatch.setattr(smtpd_handler, "handle_EHLO", ehlo_response, raising=False)

    async with smtpd_client:
        assert smtpd_client.is_ehlo_or_helo_needed is True

        await smtpd_client._ehlo_or_helo_if_needed()

        assert smtpd_client.is_ehlo_or_helo_needed is False


async def test_ehlo_or_helo_if_needed_neither_succeeds(
    smtpd_client, smtpd_handler, monkeypatch
):
    async def ehlo_or_helo_response(self, session, envelope, hostname):
        return "500 no bueno"

    monkeypatch.setattr(
        smtpd_handler, "handle_EHLO", ehlo_or_helo_response, raising=False
    )
    monkeypatch.setattr(
        smtpd_handler, "handle_HELO", ehlo_or_helo_response, raising=False
    )

    async with smtpd_client:
        assert smtpd_client.is_ehlo_or_helo_needed is True

        with pytest.raises(SMTPHeloError):
            await smtpd_client._ehlo_or_helo_if_needed()


async def test_ehlo_or_helo_if_needed_disconnect_on_ehlo(
    smtpd_client,
    smtpd_handler,
    smtpd_server,
    monkeypatch,
    smtpd_commands,
    smtpd_responses,
):
    async def ehlo_or_helo_response(*args):
        smtpd_server.close()
        await smtpd_server.wait_closed()

        return "501 oh noes"

    monkeypatch.setattr(
        smtpd_handler, "handle_EHLO", ehlo_or_helo_response, raising=False
    )
    monkeypatch.setattr(
        smtpd_handler, "handle_HELO", ehlo_or_helo_response, raising=False
    )

    async with smtpd_client:
        with pytest.raises(SMTPHeloError):
            await smtpd_client._ehlo_or_helo_if_needed()


async def test_rset_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.rset()

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_rset_error(smtpd_client, smtpd_handler, monkeypatch):
    async def rset_response(self, session, envelope):
        return "501 oh noes"

    monkeypatch.setattr(smtpd_handler, "handle_RSET", rset_response, raising=False)

    async with smtpd_client:
        with pytest.raises(SMTPResponseException):
            await smtpd_client.rset()


async def test_noop_ok(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.noop()

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_noop_error(smtpd_client, smtpd_handler, monkeypatch):
    async def noop_response(self, session, envelope, arg):
        return "501 oh noes"

    monkeypatch.setattr(smtpd_handler, "handle_NOOP", noop_response, raising=False)

    async with smtpd_client:
        with pytest.raises(SMTPResponseException):
            await smtpd_client.noop()


async def test_vrfy_ok(smtpd_client):
    nice_address = "test@example.com"
    async with smtpd_client:
        response = await smtpd_client.vrfy(nice_address)

        assert response.code == SMTPStatus.cannot_vrfy


async def test_vrfy_with_blank_address(smtpd_client):
    bad_address = ""
    async with smtpd_client:
        with pytest.raises(SMTPResponseException):
            await smtpd_client.vrfy(bad_address)


async def test_expn_ok(smtpd_client, aiosmtpd_class, monkeypatch):
    async def expn_response(self, arg):
        await self.push(
            """250-Joseph Blow <jblow@example.com>
250 Alice Smith <asmith@example.com>"""
        )

    monkeypatch.setattr(aiosmtpd_class, "smtp_EXPN", expn_response, raising=False)

    async with smtpd_client:
        response = await smtpd_client.expn("listserv-members")
        assert response.code == SMTPStatus.completed


async def test_expn_error(smtpd_client):
    """
    Since EXPN isn't implemented by aiosmtpd, it raises an exception by default.
    """
    async with smtpd_client:
        with pytest.raises(SMTPResponseException):
            await smtpd_client.expn("a-list")


async def test_help_ok(smtpd_client):
    async with smtpd_client:
        help_message = await smtpd_client.help()

        assert "Supported commands" in help_message


async def test_help_error(smtpd_client, aiosmtpd_class, monkeypatch):
    async def help_response(self, arg):
        await self.push("501 error")

    monkeypatch.setattr(aiosmtpd_class, "smtp_HELP", help_response, raising=False)

    async with smtpd_client:
        with pytest.raises(SMTPResponseException):
            await smtpd_client.help()


async def test_quit_error(smtpd_client, smtpd_handler, monkeypatch):
    async def quit_response(self, arg):
        return "501 error"

    monkeypatch.setattr(smtpd_handler, "handle_QUIT", quit_response, raising=False)

    async with smtpd_client:
        with pytest.raises(SMTPResponseException):
            await smtpd_client.quit()


async def test_supported_methods(smtpd_client):
    async with smtpd_client:
        response = await smtpd_client.ehlo()

        assert response.code == SMTPStatus.completed
        assert smtpd_client.supports_extension("size")
        assert smtpd_client.supports_extension("help")
        assert not smtpd_client.supports_extension("bogus")


async def test_mail_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        response = await smtpd_client.mail("j@example.com")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_mail_error(smtpd_client, smtpd_handler, monkeypatch):
    async def mail_response(self, arg):
        return "501 error"

    monkeypatch.setattr(smtpd_handler, "handle_MAIL", mail_response, raising=False)

    async with smtpd_client:
        await smtpd_client.ehlo()

        with pytest.raises(SMTPResponseException):
            await smtpd_client.mail("test@example.com")


async def test_rcpt_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail("j@example.com")

        response = await smtpd_client.rcpt("test@example.com")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_rcpt_options(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b"250 ehlo OK")
        preset_client.server.responses.append(b"250 mail OK")
        preset_client.server.responses.append(b"250 rcpt OK")

        await preset_client.ehlo()
        await preset_client.mail("j@example.com")

        response = await preset_client.rcpt(
            "test@example.com", options=["NOTIFY=FAILURE,DELAY"]
        )

        assert response.code == SMTPStatus.completed


async def test_rcpt_error(smtpd_client, smtpd_handler, monkeypatch):
    async def rcpt_response(self, arg):
        return "501 error"

    monkeypatch.setattr(smtpd_handler, "handle_RCPT", rcpt_response, raising=False)

    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail("j@example.com")

        with pytest.raises(SMTPResponseException):
            await smtpd_client.rcpt("test@example.com")


async def test_data_ok(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail("j@example.com")
        await smtpd_client.rcpt("test@example.com")
        response = await smtpd_client.data("HELLO WORLD")

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_data_with_timeout_arg(smtpd_client):
    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail("j@example.com")
        await smtpd_client.rcpt("test@example.com")
        response = await smtpd_client.data("HELLO WORLD", timeout=10)

        assert response.code == SMTPStatus.completed
        assert response.message == "OK"


async def test_data_error(smtpd_client, aiosmtpd_class, monkeypatch):
    async def data_response(self, arg):
        await self.push("501 error")

    monkeypatch.setattr(aiosmtpd_class, "smtp_DATA", data_response, raising=False)

    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail("admin@example.com")
        await smtpd_client.rcpt("test@example.com")
        with pytest.raises(SMTPDataError):
            await smtpd_client.data("TEST MESSAGE")


async def test_data_complete_error(smtpd_client, smtpd_handler, monkeypatch):
    async def data_response(self, arg):
        return "501 error"

    monkeypatch.setattr(smtpd_handler, "handle_DATA", data_response, raising=False)

    async with smtpd_client:
        await smtpd_client.ehlo()
        await smtpd_client.mail("admin@example.com")
        await smtpd_client.rcpt("test@example.com")
        with pytest.raises(SMTPDataError):
            await smtpd_client.data("TEST MESSAGE")


async def test_command_timeout_error(
    smtpd_client, smtpd_handler, monkeypatch, event_loop
):
    async def ehlo_response(self, session, envelope, hostname):
        await asyncio.sleep(1, loop=event_loop)
        return "250 OK :)"

    monkeypatch.setattr(smtpd_handler, "handle_EHLO", ehlo_response, raising=False)

    async with smtpd_client:
        with pytest.raises(SMTPTimeoutError):
            await smtpd_client.ehlo(timeout=0.01)


async def test_gibberish_raises_exception(smtpd_client, smtpd_handler, monkeypatch):
    async def noop_response(self, session, envelope, arg):
        return "sdfjlfwqejflqw"

    monkeypatch.setattr(smtpd_handler, "handle_NOOP", noop_response, raising=False)

    async with smtpd_client:
        with pytest.raises(SMTPResponseException):
            await smtpd_client.noop()

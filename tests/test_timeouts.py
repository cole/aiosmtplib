"""
Timeout tests.
"""
import asyncio

import pytest

from aiosmtplib import SMTP, SMTPTimeoutError


SLEEP_LENGTH = 0.05
TIMEOUT = SLEEP_LENGTH - 0.01

pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


@pytest.fixture(scope="function")
async def slow_response(request, event_loop):
    async def response(self, *args):
        await asyncio.sleep(SLEEP_LENGTH, loop=event_loop)
        return "250 OK, just a bit slow."

    return response


async def test_command_timeout_error(
    smtp_client, smtpd_server, smtpd_handler, monkeypatch, slow_response
):
    monkeypatch.setattr(smtpd_handler, "handle_EHLO", slow_response, raising=False)

    async with smtp_client:
        with pytest.raises(SMTPTimeoutError):
            await smtp_client.ehlo(timeout=TIMEOUT)


async def test_data_timeout_error(
    smtp_client, smtpd_server, smtpd_handler, monkeypatch, slow_response
):
    monkeypatch.setattr(smtpd_handler, "handle_DATA", slow_response, raising=False)

    async with smtp_client:
        await smtp_client.ehlo()
        await smtp_client.mail("j@example.com")
        await smtp_client.rcpt("test@example.com")
        with pytest.raises(SMTPTimeoutError):
            await smtp_client.data("HELLO WORLD", timeout=TIMEOUT)


async def test_timeout_error_on_connect(
    smtp_client, smtpd_server, smtpd_class, monkeypatch, slow_response
):
    monkeypatch.setattr(smtpd_class, "_handle_client", slow_response)

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.connect(timeout=TIMEOUT)


async def test_timeout_on_initial_read(
    smtp_client, smtpd_server, smtpd_class, event_loop, monkeypatch
):
    async def slow_response(self, *args):
        await self.push("220-hi")
        await asyncio.sleep(SLEEP_LENGTH, loop=event_loop)

    monkeypatch.setattr(smtpd_class, "_handle_client", slow_response)

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.connect(timeout=TIMEOUT)


async def test_timeout_on_starttls(
    smtp_client, smtpd_server, smtpd_class, monkeypatch, slow_response
):
    monkeypatch.setattr(smtpd_class, "smtp_STARTTLS", slow_response)

    await smtp_client.connect()
    await smtp_client.ehlo()

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.starttls(validate_certs=False, timeout=TIMEOUT)

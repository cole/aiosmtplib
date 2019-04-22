"""
Timeout tests.
"""
import asyncio

import pytest

from aiosmtplib import SMTPTimeoutError


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def slow_response(self, *args):
    await asyncio.sleep(1.0)
    return "250 a bit slow"


async def test_command_timeout_error(
    smtp_client, smtpd_server, smtpd_handler, event_loop, monkeypatch
):
    monkeypatch.setattr(smtpd_handler, "handle_EHLO", slow_response, raising=False)

    await smtp_client.connect()

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.ehlo("example.com", timeout=0.01)


async def test_data_timeout_error(
    smtp_client, smtpd_server, smtpd_handler, monkeypatch
):
    monkeypatch.setattr(smtpd_handler, "handle_DATA", slow_response, raising=False)

    await smtp_client.connect()
    await smtp_client.ehlo()
    await smtp_client.mail("j@example.com")
    await smtp_client.rcpt("test@example.com")
    with pytest.raises(SMTPTimeoutError):
        await smtp_client.data("HELLO WORLD", timeout=0.01)


async def test_timeout_error_on_connect(
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    monkeypatch.setattr(smtpd_class, "_handle_client", slow_response)

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.connect(timeout=0.01)

    assert smtp_client.transport is None
    assert smtp_client.protocol is None


async def test_timeout_on_initial_read(
    smtp_client, smtpd_server, smtpd_class, event_loop, monkeypatch
):
    async def read_slow_response(self, *args):
        await self.push("220-hi")
        await asyncio.sleep(1.0, loop=event_loop)

    monkeypatch.setattr(smtpd_class, "_handle_client", read_slow_response)

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.connect(timeout=0.01)


async def test_timeout_on_starttls(smtp_client, smtpd_server, smtpd_class, monkeypatch):
    monkeypatch.setattr(smtpd_class, "smtp_STARTTLS", slow_response)

    await smtp_client.connect()
    await smtp_client.ehlo()

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.starttls(validate_certs=False, timeout=0.01)

"""
Timeout tests.
"""
import asyncio

import pytest

from aiosmtplib import (
    SMTP,
    SMTPConnectTimeoutError,
    SMTPServerDisconnected,
    SMTPStatus,
    SMTPTimeoutError,
)


pytestmark = pytest.mark.asyncio()


@pytest.fixture(scope="session")
def delayed_ok_response_handler(request):
    async def delayed_ok_response(smtpd, *args, **kwargs):
        await asyncio.sleep(1.0)
        await smtpd.push("{} all done".format(SMTPStatus.completed))

    return delayed_ok_response


@pytest.fixture(scope="session")
def delayed_read_response_handler(request):
    async def delayed_read_response(smtpd, *args, **kwargs):
        await smtpd.push("{}-hi".format(SMTPStatus.ready))
        await asyncio.sleep(1.0)

    return delayed_read_response


async def test_command_timeout_error(
    smtp_client, smtpd_server, smtpd_class, delayed_ok_response_handler, monkeypatch
):
    monkeypatch.setattr(smtpd_class, "smtp_EHLO", delayed_ok_response_handler)

    await smtp_client.connect()

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.ehlo("example.com", timeout=0.0)


async def test_data_timeout_error(
    smtp_client, smtpd_server, smtpd_class, delayed_ok_response_handler, monkeypatch
):
    monkeypatch.setattr(smtpd_class, "smtp_DATA", delayed_ok_response_handler)

    await smtp_client.connect()
    await smtp_client.ehlo()
    await smtp_client.mail("j@example.com")
    await smtp_client.rcpt("test@example.com")
    with pytest.raises(SMTPTimeoutError):
        await smtp_client.data("HELLO WORLD", timeout=0.0)


async def test_timeout_error_on_connect(
    smtp_client, smtpd_server, smtpd_class, delayed_ok_response_handler, monkeypatch
):
    monkeypatch.setattr(smtpd_class, "_handle_client", delayed_ok_response_handler)

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.connect(timeout=0.0)

    assert smtp_client._reader is None
    assert smtp_client._writer is None


async def test_timeout_on_initial_read(
    smtp_client, smtpd_server, smtpd_class, delayed_read_response_handler, monkeypatch
):
    monkeypatch.setattr(smtpd_class, "_handle_client", delayed_read_response_handler)

    with pytest.raises(SMTPTimeoutError):
        # We need to use a timeout > 0 here to avoid timing out on connect
        await smtp_client.connect(timeout=0.01)


async def test_timeout_on_starttls(
    smtp_client, smtpd_server, smtpd_class, delayed_ok_response_handler, monkeypatch
):
    monkeypatch.setattr(smtpd_class, "smtp_STARTTLS", delayed_ok_response_handler)

    await smtp_client.connect()
    await smtp_client.ehlo()

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.starttls(validate_certs=False, timeout=0.0)


async def test_connect_timeout_error(hostname, port):
    client = SMTP(hostname=hostname, port=port, timeout=0.0)

    with pytest.raises(SMTPConnectTimeoutError) as exc:
        await client.connect()

    expected_message = "Timed out connecting to {host} on port {port}".format(
        host=hostname, port=port
    )
    assert str(exc.value) == expected_message


async def test_server_disconnected_error_after_connect_timeout(hostname, port, message):
    client = SMTP(hostname=hostname, port=port)

    with pytest.raises(SMTPConnectTimeoutError):
        await client.connect(timeout=0.0)

    with pytest.raises(SMTPServerDisconnected):
        await client.sendmail(message["From"], [message["To"]], str(message))

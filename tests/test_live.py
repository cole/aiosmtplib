"""
Tests run against live mail providers.

These aren't generally run as part of the test suite.
"""
import os
from email.message import EmailMessage

import pytest

from aiosmtplib import SMTP, SMTPAuthenticationError, SMTPStatus, send


pytestmark = [
    pytest.mark.skipif(
        os.environ.get("AIOSMTPLIB_LIVE_TESTS") != "true",
        reason="No tests against real servers unless requested",
    ),
    pytest.mark.asyncio(),
]


async def test_starttls_gmail() -> None:
    client = SMTP(hostname="smtp.gmail.com", port=587, use_tls=False)
    await client.connect(timeout=1.0)
    await client.ehlo()
    await client.starttls(validate_certs=False)
    response = await client.ehlo()

    assert response.code == SMTPStatus.completed
    assert "smtp.gmail.com at your service" in response.message
    assert client.server_auth_methods

    with pytest.raises(SMTPAuthenticationError):
        await client.login("test", "test")


@pytest.mark.asyncio()
async def test_qq_login() -> None:
    client = SMTP(hostname="smtp.qq.com", port=587, use_tls=False)
    await client.connect(timeout=2.0)
    await client.ehlo()
    await client.starttls(validate_certs=False)

    with pytest.raises(SMTPAuthenticationError):
        await client.login("test", "test")


async def test_office365_auth_send() -> None:
    message = EmailMessage()
    message["From"] = "user@mydomain.com"
    message["To"] = "somebody@example.com"
    message["Subject"] = "Hello World!"
    message.set_content("Sent via aiosmtplib")

    with pytest.raises(SMTPAuthenticationError):
        await send(
            message,
            hostname="smtp.office365.com",
            port=587,
            start_tls=True,
            password="test",
            username="test",
        )

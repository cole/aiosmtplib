"""
Tests run against live mail providers.

These aren't generally run as part of the test suite.
"""
import os

import pytest

from aiosmtplib import SMTP, SMTPAuthenticationError, SMTPStatus


pytestmark = [
    pytest.mark.skipif(
        os.environ.get("TRAVIS") == "true",
        reason="No tests against real servers on TravisCI",
    ),
    pytest.mark.asyncio(forbid_global_loop=True),
]


async def test_starttls_gmail(event_loop):
    client = SMTP(hostname="smtp.gmail.com", port=587, loop=event_loop, use_tls=False)
    await client.connect(timeout=1.0)
    await client.ehlo()
    await client.starttls(validate_certs=False)
    response = await client.ehlo()

    assert response.code == SMTPStatus.completed
    assert "smtp.gmail.com at your service" in response.message
    with pytest.raises(SMTPAuthenticationError):
        await client.login("test", "test")


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_qq_login(event_loop):
    client = SMTP(hostname="smtp.qq.com", port=587, loop=event_loop, use_tls=False)
    await client.connect(timeout=2.0)
    await client.ehlo()
    await client.starttls(validate_certs=False)

    with pytest.raises(SMTPAuthenticationError):
        await client.login("test", "test")

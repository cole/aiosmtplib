"""
Cancellation tests.
"""

import asyncio

import pytest

from aiosmtplib import SMTP, SMTPServerDisconnected, SMTPStatus

from .smtpd import mock_response_delayed_ok


@pytest.mark.smtpd_mocks(smtp_NOOP=mock_response_delayed_ok)
async def test_cancelled_command_closes_connection(smtp_client: SMTP) -> None:
    await smtp_client.connect()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(smtp_client.noop(), 0.01)

    # The reply is still in flight, so the connection can't be reused without
    # pairing that reply with the next command.
    assert smtp_client.protocol is None
    assert smtp_client.transport is None
    assert not smtp_client.is_connected

    with pytest.raises(SMTPServerDisconnected):
        await smtp_client.noop()


@pytest.mark.smtpd_mocks(smtp_DATA=mock_response_delayed_ok)
async def test_cancelled_data_closes_connection(smtp_client: SMTP) -> None:
    await smtp_client.connect()
    await smtp_client.mail("j@example.com")
    await smtp_client.rcpt("test@example.com")

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(smtp_client.data("HELLO WORLD"), 0.01)

    assert not smtp_client.is_connected


@pytest.mark.smtpd_options(tls=False)
@pytest.mark.smtpd_mocks(smtp_STARTTLS=mock_response_delayed_ok)
async def test_cancelled_starttls_closes_connection(smtp_client: SMTP) -> None:
    await smtp_client.connect()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(smtp_client.starttls(), 0.01)

    assert not smtp_client.is_connected


@pytest.mark.smtpd_mocks(smtp_EHLO=mock_response_delayed_ok)
async def test_cancel_while_waiting_for_command_lock_keeps_connection(
    smtp_client: SMTP,
) -> None:
    await smtp_client.connect()

    ehlo_task = asyncio.create_task(smtp_client.ehlo(timeout=2.0))
    await asyncio.sleep(0)
    noop_task = asyncio.create_task(smtp_client.noop())
    await asyncio.sleep(0)

    # NOOP never got as far as writing, so the connection is still in sync.
    noop_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await noop_task

    assert smtp_client.is_connected
    response = await ehlo_task
    assert response.code == SMTPStatus.completed

    response = await smtp_client.noop()
    assert response.code == SMTPStatus.completed

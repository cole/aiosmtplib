"""
Timeout tests.
"""
import asyncio

import pytest

from aiosmtplib import (
    SMTP,
    SMTPConnectTimeoutError,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)
from aiosmtplib.protocol import SMTPProtocol


pytestmark = pytest.mark.asyncio()


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
    smtp_client, smtpd_server, smtpd_class, monkeypatch
):
    async def read_slow_response(self, *args):
        await self.push("220-hi")
        await asyncio.sleep(1.0)

    monkeypatch.setattr(smtpd_class, "_handle_client", read_slow_response)

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.connect(timeout=0.01)


async def test_timeout_on_starttls(smtp_client, smtpd_server, smtpd_class, monkeypatch):
    monkeypatch.setattr(smtpd_class, "smtp_STARTTLS", slow_response)

    await smtp_client.connect()
    await smtp_client.ehlo()

    with pytest.raises(SMTPTimeoutError):
        await smtp_client.starttls(validate_certs=False, timeout=0.01)


async def test_protocol_readline_with_timeout_times_out(
    event_loop, stream_reader, echo_server, hostname, port
):
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    protocol.pause_writing()
    protocol._stream_writer.write(b"1234")

    with pytest.raises(SMTPTimeoutError) as exc:
        await protocol._stream_reader.readline_with_timeout(timeout=0.0)

    protocol._stream_writer.close()

    assert str(exc.value) == "Timed out waiting for server response"


async def test_protocol_timeout_on_drain_writer(
    event_loop, stream_reader, echo_server, hostname, port
):
    connect_future = event_loop.create_connection(
        SMTPProtocol, host=hostname, port=port
    )

    _, protocol = await asyncio.wait_for(connect_future, timeout=1.0)

    protocol._stream_writer.write(b"1234")
    protocol.pause_writing()

    with pytest.raises(SMTPTimeoutError) as exc:
        await protocol._stream_writer.drain_with_timeout(timeout=0.01)

    protocol._stream_writer.close()
    assert str(exc.value) == "Timed out on write"


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

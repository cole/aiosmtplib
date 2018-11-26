"""
Tests covering SMTP configuration options.
"""
import socket

import pytest

from aiosmtplib import SMTP


def test_tls_context_and_cert_raises():
    with pytest.raises(ValueError):
        SMTP(use_tls=True, client_cert="foo.crt", tls_context=True)


@pytest.mark.asyncio(forbid_global_loop=False)
async def test_tls_context_and_cert_to_connect_raises():
    client = SMTP(use_tls=True, tls_context=True)

    with pytest.raises(ValueError):
        await client.connect(client_cert="foo.crt")


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_tls_context_and_cert_to_starttls_raises(smtpd_client, event_loop):
    async with smtpd_client:
        with pytest.raises(ValueError):
            await smtpd_client.starttls(client_cert="test.cert", tls_context=True)


@pytest.mark.asyncio(forbid_global_loop=False)
async def test_config_via_connect_kwargs(smtpd_server, event_loop, hostname, port):
    client = SMTP(
        hostname="", use_tls=True, port=port + 1, source_address="example.com"
    )

    source_address = socket.getfqdn()
    await client.connect(
        hostname=hostname,
        port=port,
        loop=event_loop,
        use_tls=False,
        source_address=source_address,
    )
    assert client.is_connected

    assert client.hostname == hostname
    assert client.port == port
    assert client.loop == event_loop
    assert client.use_tls is False
    assert client.source_address == source_address

    await client.quit()


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_default_port_on_connect(event_loop):
    client = SMTP(loop=event_loop)

    try:
        await client.connect(use_tls=False, timeout=0.00001)
    except Exception:
        pass  # Ignore connection failure

    assert client.port == 25

    client.close()


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_default_tls_port_on_connect(event_loop):
    client = SMTP(loop=event_loop)

    try:
        await client.connect(use_tls=True, timeout=0.000001)
    except Exception:
        pass  # Ignore connection failure

    assert client.port == 465

    client.close()

"""
Tests covering SMTP configuration options.
"""
import asyncio
import socket

import pytest

from aiosmtplib import SMTP


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_tls_context_and_cert_raises():
    with pytest.raises(ValueError):
        SMTP(use_tls=True, client_cert="foo.crt", tls_context=True)


async def test_tls_context_and_cert_to_connect_raises():
    client = SMTP(use_tls=True, tls_context=True)

    with pytest.raises(ValueError):
        await client.connect(client_cert="foo.crt")


async def test_tls_context_and_cert_to_starttls_raises(
    smtp_client, smtpd_server, event_loop
):
    async with smtp_client:
        with pytest.raises(ValueError):
            await smtp_client.starttls(client_cert="test.cert", tls_context=True)


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


async def test_default_port_on_connect(event_loop):
    client = SMTP(loop=event_loop)

    try:
        await client.connect(use_tls=False, timeout=1.0)
    except (ValueError, OSError):
        pass  # Ignore connection failure

    assert client.port == 25

    client.close()


async def test_default_tls_port_on_connect(event_loop):
    client = SMTP(loop=event_loop)

    try:
        await client.connect(use_tls=True, timeout=1.0)
    except (ValueError, OSError):
        pass  # Ignore connection failure

    assert client.port == 465

    client.close()


async def test_connect_hostname_takes_precedence(
    event_loop, hostname, port, smtpd_server
):
    client = SMTP(hostname="example.com", port=port, loop=event_loop)
    await client.connect(hostname=hostname)

    assert client.hostname == hostname

    await client.quit()


async def test_connect_port_takes_precedence(event_loop, hostname, port, smtpd_server):
    client = SMTP(hostname=hostname, port=17, loop=event_loop)
    await client.connect(port=port)

    assert client.port == port

    await client.quit()


async def test_connect_timeout_takes_precedence(
    event_loop, hostname, port, smtpd_server
):
    client = SMTP(hostname=hostname, port=port, loop=event_loop, timeout=0.66)
    await client.connect(timeout=0.99)

    assert client.timeout == 0.99

    await client.quit()


async def test_connect_source_address_takes_precedence(
    event_loop, hostname, port, smtpd_server
):
    client = SMTP(
        hostname=hostname, port=port, loop=event_loop, source_address="example.com"
    )
    await client.connect(source_address=socket.getfqdn())

    assert client.source_address != "example.com"

    await client.quit()


async def test_connect_event_loop_takes_precedence(
    event_loop, hostname, port, smtpd_server
):
    init_loop = asyncio.new_event_loop()
    client = SMTP(hostname=hostname, port=port, loop=init_loop)

    await client.connect(loop=event_loop)

    assert init_loop is not event_loop
    assert client.loop is event_loop

    await client.quit()


async def test_connect_use_tls_takes_precedence(
    event_loop, hostname, port, smtpd_server
):
    client = SMTP(hostname=hostname, port=port, loop=event_loop, use_tls=True)

    await client.connect(use_tls=False)

    assert client.use_tls is False

    await client.quit()


async def test_connect_validate_certs_takes_precedence(
    event_loop, hostname, port, smtpd_server
):
    client = SMTP(hostname=hostname, port=port, loop=event_loop, validate_certs=False)

    await client.connect(validate_certs=True)

    assert client.validate_certs is True

    await client.quit()


async def test_connect_certificate_options_take_precedence(
    event_loop, hostname, port, smtpd_server
):
    client = SMTP(
        hostname=hostname,
        port=port,
        loop=event_loop,
        client_cert="test",
        client_key="test",
        cert_bundle="test",
    )

    await client.connect(client_cert=None, client_key=None, cert_bundle=None)

    assert client.client_cert is None
    assert client.client_key is None
    assert client.cert_bundle is None

    await client.quit()


async def test_connect_tls_context_option_takes_precedence(
    event_loop, hostname, port, smtpd_server, client_tls_context, server_tls_context
):
    client = SMTP(
        hostname=hostname, port=port, loop=event_loop, tls_context=server_tls_context
    )

    await client.connect(tls_context=client_tls_context)

    assert client.tls_context is client_tls_context

    await client.quit()


async def test_starttls_certificate_options_take_precedence(
    event_loop, hostname, port, smtpd_server, valid_cert_path, valid_key_path
):
    client = SMTP(
        hostname=hostname,
        port=port,
        loop=event_loop,
        validate_certs=False,
        client_cert="test1",
        client_key="test1",
        cert_bundle="test1",
    )

    await client.connect(
        validate_certs=False,
        client_cert="test2",
        client_key="test2",
        cert_bundle="test2",
    )

    await client.starttls(
        client_cert=valid_cert_path,
        client_key=valid_key_path,
        cert_bundle=valid_cert_path,
        validate_certs=True,
    )

    assert client.client_cert == valid_cert_path
    assert client.client_key == valid_key_path
    assert client.cert_bundle == valid_cert_path
    assert client.validate_certs is True

    await client.quit()

"""
TLS and STARTTLS handling.
"""
import asyncio.sslproto
import ssl
from pathlib import Path

import pytest

from aiosmtplib import (
    SMTP,
    SMTPConnectError,
    SMTPException,
    SMTPResponseException,
    SMTPStatus,
    SMTPTimeoutError,
)
from testserver import SMTPPresetServer


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)
cert_path = str(Path("tests/certs/selfsigned.crt"))
key_path = str(Path("tests/certs/selfsigned.key"))
invalid_cert_path = str(Path("tests/certs/invalid.crt"))
invalid_key_path = str(Path("tests/certs/invalid.key"))


@pytest.fixture(scope="function")
def tls_preset_server(request, event_loop, unused_tcp_port):
    server = SMTPPresetServer(
        "localhost", unused_tcp_port, loop=event_loop, use_tls=True
    )

    event_loop.run_until_complete(server.start())

    def close_server():
        event_loop.run_until_complete(server.stop())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def tls_preset_client(request, tls_preset_server, event_loop):
    client = SMTP(
        hostname=tls_preset_server.hostname,
        port=tls_preset_server.port,
        loop=event_loop,
        use_tls=True,
        validate_certs=False,
        timeout=1,
    )
    client.server = tls_preset_server

    return client


async def test_tls_connection(tls_preset_client):
    """
    Use an explicit connect/quit here, as other tests use the context manager.
    """
    await tls_preset_client.connect()
    assert tls_preset_client.is_connected

    await tls_preset_client.quit()
    assert not tls_preset_client.is_connected


async def test_starttls(preset_client):
    async with preset_client:
        preset_client.server.responses.append(
            b"\n".join([b"250-localhost, hello", b"250-SIZE 100000", b"250 STARTTLS"])
        )
        preset_client.server.responses.append(b"220 ready for TLS")
        response = await preset_client.starttls(validate_certs=False)

        assert response.code == SMTPStatus.ready

        # Make sure our state has been cleared
        assert not preset_client.esmtp_extensions
        assert not preset_client.supported_auth_methods
        assert not preset_client.supports_esmtp

        # make sure our connection was actually upgraded
        assert isinstance(
            preset_client.transport, asyncio.sslproto._SSLProtocolTransport
        )

        preset_client.server.responses.append(b"250 all good")
        response = await preset_client.ehlo()
        assert response.code == SMTPStatus.completed


async def test_starttls_timeout(preset_client):
    async with preset_client:
        preset_client.server.responses.append(
            b"\n".join([b"250-localhost, hello", b"250-SIZE 100000", b"250 STARTTLS"])
        )
        await preset_client.ehlo()

        preset_client.server.delay_next_response = 1

        with pytest.raises(SMTPTimeoutError):
            await preset_client.starttls(validate_certs=False, timeout=0.001)


async def test_starttls_with_explicit_server_hostname(preset_client):
    async with preset_client:
        preset_client.server.responses.append(
            b"\n".join([b"250-localhost, hello", b"250-SIZE 100000", b"250 STARTTLS"])
        )
        await preset_client.ehlo()

        preset_client.server.responses.append(b"220 ready for TLS")
        await preset_client.starttls(
            validate_certs=False, server_hostname="example.com"
        )


async def test_starttls_not_supported(preset_client):
    async with preset_client:
        preset_client.server.responses.append(
            b"\n".join([b"250-localhost, hello", b"250 SIZE 100000"])
        )
        await preset_client.ehlo()

        with pytest.raises(SMTPException):
            await preset_client.starttls(validate_certs=False)


async def test_starttls_not_ready(preset_client):
    async with preset_client:
        preset_client.server.responses.append(
            b"\n".join([b"250-localhost, hello", b"250-SIZE 100000", b"250 STARTTLS"])
        )
        preset_client.server.responses.append(b"451 oh no")
        with pytest.raises(SMTPResponseException):
            await preset_client.starttls(validate_certs=False)

        # Make sure our state has been _not_ been cleared
        assert "starttls" in preset_client.esmtp_extensions
        assert preset_client.supports_esmtp

        # make sure our connection wasn't upgraded
        assert not isinstance(
            preset_client.transport, asyncio.sslproto._SSLProtocolTransport
        )


async def test_starttls_bad_response_preserves_state(preset_client):
    async with preset_client:
        preset_client.server.responses.append(
            b"\n".join(
                [b"250-localhost, hello", b"250-AUTH LOGIN BOGUS", b"250 STARTTLS"]
            )
        )
        await preset_client.ehlo()

        preset_client.server.responses.append(b"555 uh oh")
        with pytest.raises(SMTPResponseException):
            await preset_client.starttls(validate_certs=False)

        # Make sure our state has *not* been cleared
        assert preset_client.esmtp_extensions
        assert preset_client.supported_auth_methods
        assert preset_client.supports_esmtp is True


async def test_starttls_with_client_cert(preset_client):
    async with preset_client:
        preset_client.server.responses.append(
            b"\n".join([b"250-localhost, hello", b"250 STARTTLS"])
        )
        preset_client.server.responses.append(b"220 ready for TLS")
        response = await preset_client.starttls(
            client_cert=cert_path, client_key=key_path, cert_bundle=cert_path
        )

        assert response.code == SMTPStatus.ready
        assert preset_client.client_cert == cert_path
        assert preset_client.client_key == key_path
        assert preset_client.cert_bundle == cert_path


async def test_starttls_with_invalid_client_cert(preset_client):
    async with preset_client:
        preset_client.server.responses.append(
            b"\n".join([b"250-localhost, hello", b"250 STARTTLS"])
        )
        with pytest.raises(ssl.SSLError):
            await preset_client.starttls(
                client_cert=invalid_cert_path,
                client_key=invalid_key_path,
                cert_bundle=invalid_cert_path,
            )


async def test_starttls_cert_error(preset_client):
    async with preset_client:
        preset_client.server.responses.append(
            b"\n".join([b"250-localhost, hello", b"250-SIZE 100000", b"250 STARTTLS"])
        )
        preset_client.server.responses.append(b"220 ready for TLS")
        with pytest.raises(ssl.SSLError):
            await preset_client.starttls(validate_certs=True)


async def test_tls_get_transport_info(tls_preset_client):
    async with tls_preset_client:
        compression = tls_preset_client.get_transport_info("compression")
        assert compression is None  # Compression is not used here

        peername = tls_preset_client.get_transport_info("peername")
        assert peername[0] == "127.0.0.1"
        assert peername[1] == tls_preset_client.port

        sock = tls_preset_client.get_transport_info("socket")
        assert sock is not None

        sockname = tls_preset_client.get_transport_info("sockname")
        assert sockname is not None

        cipher = tls_preset_client.get_transport_info("cipher")
        assert cipher is not None

        peercert = tls_preset_client.get_transport_info("peercert")
        assert peercert is not None

        sslcontext = tls_preset_client.get_transport_info("sslcontext")
        assert sslcontext is not None

        sslobj = tls_preset_client.get_transport_info("ssl_object")
        assert sslobj is not None


async def test_tls_smtp_connect_to_non_tls_server(preset_server, event_loop):
    tls_client = SMTP(
        hostname="127.0.0.1",
        port=preset_server.port,
        loop=event_loop,
        use_tls=True,
        validate_certs=False,
    )

    with pytest.raises(SMTPConnectError):
        await tls_client.connect()
    assert not tls_client.is_connected


async def test_tls_connection_with_existing_sslcontext(tls_preset_client):
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    await tls_preset_client.connect(tls_context=context)
    assert tls_preset_client.is_connected

    assert tls_preset_client.tls_context is context

    await tls_preset_client.quit()
    assert not tls_preset_client.is_connected


async def test_tls_connection_with_client_cert(tls_preset_client):
    await tls_preset_client.connect(
        hostname="localhost",
        validate_certs=True,
        client_cert=cert_path,
        client_key=key_path,
        cert_bundle=cert_path,
    )
    assert tls_preset_client.is_connected

    await tls_preset_client.quit()
    assert not tls_preset_client.is_connected


async def test_tls_connection_with_cert_error(tls_preset_client):
    with pytest.raises(SMTPConnectError) as exception_info:
        await tls_preset_client.connect(validate_certs=True)

    assert "CERTIFICATE_VERIFY_FAILED" in str(exception_info.value)

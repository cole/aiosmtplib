"""
TLS and STARTTLS handling.
"""
import asyncio
import copy
import ssl
from typing import Callable, Type

import pytest
from aiosmtpd.smtp import SMTP as SMTPD

from aiosmtplib import (
    SMTP,
    SMTPConnectError,
    SMTPException,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPStatus,
)


pytestmark = pytest.mark.asyncio()


async def test_tls_connection(
    smtp_client_tls: SMTP, smtpd_server_tls: asyncio.AbstractServer
) -> None:
    """
    Use an explicit connect/quit here, as other tests use the context manager.
    """
    await smtp_client_tls.connect()
    assert smtp_client_tls.is_connected

    await smtp_client_tls.quit()
    assert not smtp_client_tls.is_connected


async def test_starttls(
    smtp_client: SMTP, smtpd_server: asyncio.AbstractServer
) -> None:
    async with smtp_client:
        response = await smtp_client.starttls()

        assert response.code == SMTPStatus.ready

        # Make sure our state has been cleared
        assert not smtp_client.esmtp_extensions
        assert not smtp_client.supported_auth_methods
        assert not smtp_client.supports_esmtp

        # Make sure our connection was actually upgraded. ssl protocol transport is
        # private in UVloop, so just check the class name.
        assert "SSL" in type(smtp_client.transport).__name__

        response = await smtp_client.ehlo()
        assert response.code == SMTPStatus.completed


async def test_starttls_init_kwarg(
    hostname: str, smtpd_server_port: int, client_tls_context: ssl.SSLContext
) -> None:
    smtp_client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=True,
        tls_context=client_tls_context,
    )

    async with smtp_client:
        # Make sure our connection was actually upgraded. ssl protocol transport is
        # private in UVloop, so just check the class name.
        assert "SSL" in type(smtp_client.transport).__name__


async def test_starttls_connect_kwarg(
    smtp_client: SMTP, smtpd_server: asyncio.AbstractServer
) -> None:
    await smtp_client.connect(start_tls=True)

    # Make sure our connection was actually upgraded. ssl protocol transport is
    # private in UVloop, so just check the class name.
    assert "SSL" in type(smtp_client.transport).__name__

    await smtp_client.quit()


async def test_starttls_auto(
    hostname: str, smtpd_server_port: int, client_tls_context: ssl.SSLContext
) -> None:
    smtp_client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=None,
        tls_context=client_tls_context,
    )

    async with smtp_client:
        # Make sure our connection was actually upgraded. ssl protocol transport is
        # private in UVloop, so just check the class name.
        assert "SSL" in type(smtp_client.transport).__name__


async def test_starttls_auto_connect_kwarg(
    hostname: str,
    smtpd_server_port: int,
    smtpd_server: asyncio.AbstractServer,
    client_tls_context: ssl.SSLContext,
) -> None:
    smtp_client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=False,
        tls_context=client_tls_context,
    )

    await smtp_client.connect(start_tls=None)

    # Make sure our connection was actually upgraded. ssl protocol transport is
    # private in UVloop, so just check the class name.
    assert "SSL" in type(smtp_client.transport).__name__

    await smtp_client.quit()


async def test_starttls_with_explicit_server_hostname(
    smtp_client: SMTP, hostname: str, smtpd_server: asyncio.AbstractServer
) -> None:
    async with smtp_client:
        await smtp_client.ehlo()

        await smtp_client.starttls(server_hostname=hostname)


async def test_starttls_not_supported(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_ehlo_minimal: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtpd_class, "smtp_EHLO", smtpd_mock_response_ehlo_minimal)

    async with smtp_client:
        await smtp_client.ehlo()

        with pytest.raises(SMTPException):
            await smtp_client.starttls()


async def test_starttls_advertised_but_not_supported(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_tls_not_available: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        smtpd_class, "smtp_STARTTLS", smtpd_mock_response_tls_not_available
    )

    async with smtp_client:
        await smtp_client.ehlo()

        with pytest.raises(SMTPException):
            await smtp_client.starttls()


async def test_starttls_disconnect_before_upgrade(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_tls_ready_disconnect: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        smtpd_class, "smtp_STARTTLS", smtpd_mock_response_tls_ready_disconnect
    )

    async with smtp_client:
        with pytest.raises(SMTPServerDisconnected):
            await smtp_client.starttls()


async def test_starttls_invalid_responses(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    smtpd_class: Type[SMTPD],
    smtpd_mock_response_error_with_code: Callable,
    monkeypatch: pytest.MonkeyPatch,
    error_code: int,
) -> None:
    monkeypatch.setattr(
        smtpd_class, "smtp_STARTTLS", smtpd_mock_response_error_with_code
    )

    async with smtp_client:
        await smtp_client.ehlo()

        old_extensions = copy.copy(smtp_client.esmtp_extensions)

        with pytest.raises(SMTPResponseException) as exception_info:
            await smtp_client.starttls()

        assert exception_info.value.code == error_code
        # Make sure our state has been _not_ been cleared
        assert smtp_client.esmtp_extensions == old_extensions
        assert smtp_client.supports_esmtp is True

        # Make sure our connection was not upgraded. ssl protocol transport is
        # private in UVloop, so just check the class name.
        assert "SSL" not in type(smtp_client.transport).__name__


async def test_starttls_with_client_cert(
    smtpd_server: asyncio.AbstractServer,
    hostname: str,
    smtpd_server_port: int,
    ca_cert_path: str,
    valid_cert_path: str,
    valid_key_path: str,
) -> None:
    smtp_client = SMTP(hostname=hostname, port=smtpd_server_port, start_tls=False)
    async with smtp_client:
        response = await smtp_client.starttls(
            client_cert=valid_cert_path,
            client_key=valid_key_path,
            cert_bundle=ca_cert_path,
        )

        assert response.code == SMTPStatus.ready
        assert smtp_client.client_cert == valid_cert_path
        assert smtp_client.client_key == valid_key_path
        assert smtp_client.cert_bundle == ca_cert_path


async def test_starttls_with_invalid_client_cert(
    smtpd_server: asyncio.AbstractServer,
    hostname: str,
    smtpd_server_port: int,
    invalid_cert_path: str,
    invalid_key_path: str,
) -> None:
    smtp_client = SMTP(hostname=hostname, port=smtpd_server_port, start_tls=False)
    async with smtp_client:
        with pytest.raises(ssl.SSLError):
            await smtp_client.starttls(
                client_cert=invalid_cert_path,
                client_key=invalid_key_path,
                cert_bundle=invalid_cert_path,
            )


async def test_starttls_with_invalid_client_cert_no_validate(
    smtpd_server: asyncio.AbstractServer,
    hostname: str,
    smtpd_server_port: int,
    invalid_cert_path: str,
    invalid_key_path: str,
) -> None:
    smtp_client = SMTP(hostname=hostname, port=smtpd_server_port, start_tls=False)
    async with smtp_client:
        response = await smtp_client.starttls(
            client_cert=invalid_cert_path,
            client_key=invalid_key_path,
            cert_bundle=invalid_cert_path,
            validate_certs=False,
        )

        assert response.code == SMTPStatus.ready
        assert smtp_client.client_cert == invalid_cert_path
        assert smtp_client.client_key == invalid_key_path
        assert smtp_client.cert_bundle == invalid_cert_path


async def test_starttls_cert_error(
    smtpd_server: asyncio.AbstractServer,
    hostname: str,
    smtpd_server_port: int,
    unknown_client_tls_context: ssl.SSLContext,
) -> None:
    smtp_client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=False,
        tls_context=unknown_client_tls_context,
    )
    async with smtp_client:
        with pytest.raises(ssl.SSLError):
            await smtp_client.starttls()


async def test_starttls_already_upgraded_error(
    smtpd_server: asyncio.AbstractServer,
    hostname: str,
    smtpd_server_port: int,
    client_tls_context: ssl.SSLContext,
) -> None:
    smtp_client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        tls_context=client_tls_context,
    )
    async with smtp_client:
        with pytest.raises(SMTPException, match="Connection already using TLS"):
            await smtp_client.starttls()


async def test_starttls_cert_no_validate(
    smtpd_server: asyncio.AbstractServer,
    hostname: str,
    smtpd_server_port: int,
    unknown_client_tls_context: ssl.SSLContext,
) -> None:
    smtp_client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=False,
        validate_certs=False,
    )
    async with smtp_client:
        response = await smtp_client.starttls()

    assert response.code == SMTPStatus.ready


async def test_tls_get_transport_info(
    smtp_client_tls: SMTP,
    hostname: str,
    smtpd_server_tls_port: int,
) -> None:
    async with smtp_client_tls:
        compression = smtp_client_tls.get_transport_info("compression")
        assert compression is None  # Compression is not used here

        peername = smtp_client_tls.get_transport_info("peername")
        assert peername[0] in ("127.0.0.1", "::1")  # IP v4 and 6
        assert peername[1] == smtpd_server_tls_port

        sock = smtp_client_tls.get_transport_info("socket")
        assert sock is not None

        sockname = smtp_client_tls.get_transport_info("sockname")
        assert sockname is not None

        cipher = smtp_client_tls.get_transport_info("cipher")
        assert cipher is not None

        peercert = smtp_client_tls.get_transport_info("peercert")
        assert peercert is not None

        sslcontext = smtp_client_tls.get_transport_info("sslcontext")
        assert sslcontext is not None

        sslobj = smtp_client_tls.get_transport_info("ssl_object")
        assert sslobj is not None


async def test_tls_smtp_connect_to_non_tls_server(
    smtp_client_tls: SMTP,
    smtpd_server_port: int,
) -> None:
    with pytest.raises(SMTPConnectError):
        await smtp_client_tls.connect(port=smtpd_server_port)
    assert not smtp_client_tls.is_connected


async def test_tls_connection_with_existing_sslcontext(
    smtp_client_tls: SMTP,
    smtpd_server_tls: asyncio.AbstractServer,
    client_tls_context: ssl.SSLContext,
) -> None:
    await smtp_client_tls.connect(tls_context=client_tls_context)
    assert smtp_client_tls.is_connected

    assert smtp_client_tls.tls_context is client_tls_context

    await smtp_client_tls.quit()
    assert not smtp_client_tls.is_connected


async def test_tls_connection_with_client_cert(
    smtpd_server_tls: asyncio.AbstractServer,
    hostname: str,
    smtpd_server_tls_port: int,
    ca_cert_path: str,
    valid_cert_path: str,
    valid_key_path: str,
) -> None:
    smtp_client_tls = SMTP(hostname=hostname, port=smtpd_server_tls_port, use_tls=True)
    await smtp_client_tls.connect(
        hostname=hostname,
        client_cert=valid_cert_path,
        client_key=valid_key_path,
        cert_bundle=ca_cert_path,
    )
    assert smtp_client_tls.is_connected

    await smtp_client_tls.quit()
    assert not smtp_client_tls.is_connected


async def test_tls_connection_with_cert_error(
    smtpd_server_tls: asyncio.AbstractServer,
    hostname: str,
    smtpd_server_tls_port: int,
) -> None:
    smtp_client_tls = SMTP(hostname=hostname, port=smtpd_server_tls_port, use_tls=True)

    with pytest.raises(SMTPConnectError) as exception_info:
        await smtp_client_tls.connect()

    assert "CERTIFICATE" in str(exception_info.value).upper()

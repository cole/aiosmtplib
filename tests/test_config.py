"""
Tests covering SMTP configuration options.
"""
import asyncio
import socket
import ssl

import pytest

from aiosmtplib import SMTP


pytestmark = pytest.mark.asyncio()


async def test_tls_context_and_cert_raises(
    client_tls_context: ssl.SSLContext,
) -> None:
    with pytest.raises(ValueError):
        SMTP(use_tls=True, client_cert="foo.crt", tls_context=client_tls_context)


async def test_tls_context_and_cert_to_connect_raises(
    client_tls_context: ssl.SSLContext,
) -> None:
    client = SMTP(use_tls=True, tls_context=client_tls_context)

    with pytest.raises(ValueError):
        await client.connect(client_cert="foo.crt")


async def test_tls_context_and_cert_to_starttls_raises(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    client_tls_context: ssl.SSLContext,
) -> None:
    async with smtp_client:
        with pytest.raises(ValueError):
            await smtp_client.starttls(
                client_cert="test.cert", tls_context=client_tls_context
            )


async def test_use_tls_and_start_tls_raises() -> None:
    with pytest.raises(ValueError):
        SMTP(use_tls=True, start_tls=True)


async def test_use_tls_and_start_tls_to_connect_raises() -> None:
    client = SMTP(use_tls=True)

    with pytest.raises(ValueError):
        await client.connect(start_tls=True)


async def test_socket_and_hostname_raises() -> None:
    with pytest.raises(ValueError):
        SMTP(hostname="example.com", sock=socket.socket(socket.AF_INET))


async def test_socket_and_port_raises() -> None:
    with pytest.raises(ValueError):
        SMTP(port=1, sock=socket.socket(socket.AF_INET))


async def test_socket_and_socket_path_raises() -> None:
    with pytest.raises(ValueError):
        SMTP(socket_path="/tmp/test", sock=socket.socket(socket.AF_INET))  # nosec


async def test_hostname_and_socket_path_raises() -> None:
    with pytest.raises(ValueError):
        SMTP(hostname="example.com", socket_path="/tmp/test")  # nosec


async def test_port_and_socket_path_raises() -> None:
    with pytest.raises(ValueError):
        SMTP(port=1, socket_path="/tmp/test")  # nosec


async def test_config_via_connect_kwargs(
    bind_address: str, unused_tcp_port: int, hostname: str, smtpd_server_port: int
) -> None:
    client = SMTP(
        hostname="",
        use_tls=True,
        start_tls=None,
        port=smtpd_server_port + 1,
        local_hostname="example.com",
    )

    local_hostname = "smtp.example.com"
    source_address = (bind_address, unused_tcp_port)
    await client.connect(
        hostname=hostname,
        port=smtpd_server_port,
        use_tls=False,
        start_tls=False,
        local_hostname=local_hostname,
        source_address=source_address,
    )
    assert client.is_connected

    assert client.hostname == hostname
    assert client.port == smtpd_server_port
    assert client.use_tls is False
    assert client.local_hostname == local_hostname
    assert client.source_address == source_address
    assert client._start_tls_on_connect is False

    await client.quit()


@pytest.mark.parametrize(
    "use_tls,start_tls,expected_port",
    [(False, False, 25), (True, False, 465), (False, True, 587)],
    ids=["plaintext", "tls", "starttls"],
)
async def test_default_port_on_connect(
    bind_address: str,
    use_tls: bool,
    start_tls: bool,
    expected_port: int,
) -> None:
    client = SMTP()

    try:
        await client.connect(
            hostname=bind_address, use_tls=use_tls, start_tls=start_tls, timeout=0.001
        )
    except (asyncio.TimeoutError, OSError):
        pass

    assert client.port == expected_port

    client.close()


async def test_connect_hostname_takes_precedence(
    hostname: str,
    smtpd_server_port: int,
) -> None:
    client = SMTP(hostname="example.com", port=smtpd_server_port, start_tls=False)
    await client.connect(hostname=hostname)

    assert client.hostname == hostname

    await client.quit()


async def test_connect_port_takes_precedence(
    hostname: str,
    smtpd_server_port: int,
) -> None:
    client = SMTP(hostname=hostname, port=17, start_tls=False)
    await client.connect(port=smtpd_server_port)

    assert client.port == smtpd_server_port

    await client.quit()


async def test_connect_timeout_is_reverted(
    hostname: str,
    smtpd_server_port: int,
) -> None:
    client = SMTP(
        hostname=hostname, port=smtpd_server_port, timeout=0.66, start_tls=False
    )
    await client.connect(timeout=0.99)

    assert client.timeout == 0.66

    await client.quit()


async def test_connect_source_address_takes_precedence(
    bind_address: str,
    unused_tcp_port: int,
    hostname: str,
    smtpd_server_port: int,
) -> None:
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=False,
        source_address=("example.com", 444),
    )
    await client.connect(source_address=(bind_address, unused_tcp_port))

    assert client.source_address == (bind_address, unused_tcp_port)

    await client.quit()


async def test_connect_local_hostname_takes_precedence(
    hostname: str,
    smtpd_server_port: int,
) -> None:
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=False,
        local_hostname="foo.com",
    )
    await client.connect(local_hostname="example.com")

    assert client.local_hostname == "example.com"

    await client.quit()


async def test_connect_deprecated_source_address(
    hostname: str,
    smtpd_server_port: int,
) -> None:
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=False,
    )
    with pytest.warns(DeprecationWarning):
        await client.connect(source_address="example.com")  # type: ignore

    assert client.local_hostname == "example.com"

    await client.quit()


async def test_connect_use_tls_takes_precedence(
    hostname: str,
    smtpd_server_port: int,
    client_tls_context: ssl.SSLContext,
) -> None:
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        use_tls=True,
        tls_context=client_tls_context,
    )

    await client.connect(use_tls=False)

    assert client.use_tls is False

    await client.quit()


async def test_connect_validate_certs_takes_precedence(
    hostname: str,
    smtpd_server_port: int,
    client_tls_context: ssl.SSLContext,
) -> None:
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        validate_certs=False,
        tls_context=client_tls_context,
    )

    await client.connect(validate_certs=True)

    assert client.validate_certs is True

    await client.quit()


async def test_connect_certificate_options_take_precedence(
    hostname: str,
    smtpd_server_port: int,
    client_tls_context: ssl.SSLContext,
) -> None:
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        client_cert="test",
        client_key="test",
        cert_bundle="test",
        start_tls=False,
    )

    await client.connect(client_cert=None, client_key=None, cert_bundle=None)

    assert client.client_cert is None
    assert client.client_key is None
    assert client.cert_bundle is None

    await client.quit()


async def test_connect_tls_context_option_takes_precedence(
    hostname: str,
    smtpd_server_port: int,
    client_tls_context: ssl.SSLContext,
    server_tls_context: ssl.SSLContext,
) -> None:
    client = SMTP(
        hostname=hostname, port=smtpd_server_port, tls_context=server_tls_context
    )

    await client.connect(tls_context=client_tls_context)

    assert client.tls_context is client_tls_context

    await client.quit()


async def test_starttls_certificate_options_take_precedence(
    hostname: str,
    smtpd_server_port: int,
    ca_cert_path: str,
    valid_cert_path: str,
    valid_key_path: str,
) -> None:
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        start_tls=False,
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
        cert_bundle=ca_cert_path,
        validate_certs=True,
    )

    assert client.client_cert == valid_cert_path
    assert client.client_key == valid_key_path
    assert client.cert_bundle == ca_cert_path
    assert client.validate_certs is True

    await client.quit()


async def test_source_address_deprecation_warning_init() -> None:
    with pytest.warns(DeprecationWarning):
        client = SMTP(source_address="example.com")  # type: ignore

    assert client.local_hostname == "example.com"


async def test_hostname_newline_raises_error() -> None:
    with pytest.raises(ValueError):
        SMTP(hostname="localhost\r\n")


async def test_local_hostname_newline_raises_error() -> None:
    with pytest.raises(ValueError):
        SMTP(
            hostname="localhost",
            local_hostname="localhost\r\nRCPT TO: <hacker@hackers.org>",
        )

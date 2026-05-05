"""
Tests for the PROXY protocol header encoder and SMTP integration.
"""

import asyncio
import struct
from ipaddress import IPv4Address, IPv6Address
from typing import Any

import pytest

from aiosmtplib import SMTP, SMTPConnectError, SMTPConnectTimeoutError
from aiosmtplib.proxy import ProxyConfig

from .smtpd import RecordingHandler


V2_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"


def test_v1_tcp4_encode() -> None:
    config = ProxyConfig(
        source=(IPv4Address("192.0.2.1"), 51234),
        destination=(IPv4Address("203.0.113.5"), 25),
        version=1,
    )
    assert config.encode() == b"PROXY TCP4 192.0.2.1 203.0.113.5 51234 25\r\n"


def test_v1_tcp6_encode() -> None:
    config = ProxyConfig(
        source=(IPv6Address("2001:db8::1"), 51234),
        destination=(IPv6Address("2001:db8::5"), 25),
        version=1,
    )
    assert config.encode() == b"PROXY TCP6 2001:db8::1 2001:db8::5 51234 25\r\n"


def test_v1_unknown_encode() -> None:
    config = ProxyConfig(version=1)
    assert config.encode() == b"PROXY UNKNOWN\r\n"


def test_v2_default_version() -> None:
    assert ProxyConfig().version == 2


def test_v2_tcp4_encode() -> None:
    config = ProxyConfig(
        source=(IPv4Address("192.0.2.1"), 51234),
        destination=(IPv4Address("203.0.113.5"), 25),
    )
    expected = (
        V2_SIGNATURE
        + struct.pack("!BBH", 0x21, 0x11, 12)
        + IPv4Address("192.0.2.1").packed
        + IPv4Address("203.0.113.5").packed
        + struct.pack("!HH", 51234, 25)
    )
    assert config.encode() == expected


def test_v2_tcp6_encode() -> None:
    config = ProxyConfig(
        source=(IPv6Address("2001:db8::1"), 51234),
        destination=(IPv6Address("2001:db8::5"), 25),
    )
    expected = (
        V2_SIGNATURE
        + struct.pack("!BBH", 0x21, 0x21, 36)
        + IPv6Address("2001:db8::1").packed
        + IPv6Address("2001:db8::5").packed
        + struct.pack("!HH", 51234, 25)
    )
    assert config.encode() == expected


def test_v2_local_encode() -> None:
    config = ProxyConfig()
    expected = V2_SIGNATURE + struct.pack("!BBH", 0x20, 0x00, 0)
    assert config.encode() == expected


def test_v2_tlvs_appended_to_payload() -> None:
    tlvs = b"\x01\x00\x03foo"
    config = ProxyConfig(
        source=(IPv4Address("192.0.2.1"), 51234),
        destination=(IPv4Address("203.0.113.5"), 25),
        tlvs=tlvs,
    )
    expected = (
        V2_SIGNATURE
        + struct.pack("!BBH", 0x21, 0x11, 12 + len(tlvs))
        + IPv4Address("192.0.2.1").packed
        + IPv4Address("203.0.113.5").packed
        + struct.pack("!HH", 51234, 25)
        + tlvs
    )
    assert config.encode() == expected


def test_v2_local_with_tlvs() -> None:
    tlvs = b"\x05\x00\x04abcd"
    config = ProxyConfig(tlvs=tlvs)
    expected = V2_SIGNATURE + struct.pack("!BBH", 0x20, 0x00, len(tlvs)) + tlvs
    assert config.encode() == expected


def test_tlvs_rejected_for_v1() -> None:
    with pytest.raises(ValueError, match="TLVs"):
        ProxyConfig(
            source=(IPv4Address("192.0.2.1"), 51234),
            destination=(IPv4Address("203.0.113.5"), 25),
            version=1,
            tlvs=b"\x01\x00\x00",
        )


def test_mixed_family_rejected() -> None:
    with pytest.raises(ValueError, match="same address family"):
        ProxyConfig(
            source=(IPv4Address("192.0.2.1"), 51234),
            destination=(IPv6Address("2001:db8::5"), 25),
        )


def test_source_without_destination_rejected() -> None:
    with pytest.raises(ValueError, match="both"):
        ProxyConfig(source=(IPv4Address("192.0.2.1"), 51234))


def test_destination_without_source_rejected() -> None:
    with pytest.raises(ValueError, match="both"):
        ProxyConfig(destination=(IPv4Address("203.0.113.5"), 25))


def test_invalid_version_rejected() -> None:
    with pytest.raises(ValueError, match="version"):
        ProxyConfig(version=3)  # type: ignore[arg-type]


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_proxy_v2_tcp4(
    hostname: str, smtpd_server_port: int, smtpd_handler: RecordingHandler
) -> None:
    config = ProxyConfig(
        source=(IPv4Address("192.0.2.1"), 51234),
        destination=(IPv4Address("203.0.113.5"), 25),
    )
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=3.0,
        start_tls=False,
        proxy_protocol=config,
    )
    async with client:
        pass

    assert smtpd_handler.proxy_data is not None
    assert smtpd_handler.proxy_data.version == 2
    assert smtpd_handler.proxy_data.src_addr == IPv4Address("192.0.2.1")
    assert smtpd_handler.proxy_data.src_port == 51234
    assert smtpd_handler.proxy_data.dst_addr == IPv4Address("203.0.113.5")
    assert smtpd_handler.proxy_data.dst_port == 25


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_proxy_v2_tcp6(
    hostname: str, smtpd_server_port: int, smtpd_handler: RecordingHandler
) -> None:
    config = ProxyConfig(
        source=(IPv6Address("2001:db8::1"), 51234),
        destination=(IPv6Address("2001:db8::5"), 25),
    )
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=3.0,
        start_tls=False,
        proxy_protocol=config,
    )
    async with client:
        pass

    assert smtpd_handler.proxy_data is not None
    assert smtpd_handler.proxy_data.version == 2
    assert smtpd_handler.proxy_data.src_addr == IPv6Address("2001:db8::1")
    assert smtpd_handler.proxy_data.src_port == 51234
    assert smtpd_handler.proxy_data.dst_addr == IPv6Address("2001:db8::5")
    assert smtpd_handler.proxy_data.dst_port == 25


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_proxy_v2_local(
    hostname: str, smtpd_server_port: int, smtpd_handler: RecordingHandler
) -> None:
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=3.0,
        start_tls=False,
        proxy_protocol=ProxyConfig(),
    )
    async with client:
        pass

    assert smtpd_handler.proxy_data is not None
    assert smtpd_handler.proxy_data.version == 2
    assert smtpd_handler.proxy_data.src_addr is None
    assert smtpd_handler.proxy_data.dst_addr is None


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_proxy_v1_tcp4(
    hostname: str, smtpd_server_port: int, smtpd_handler: RecordingHandler
) -> None:
    config = ProxyConfig(
        source=(IPv4Address("192.0.2.1"), 51234),
        destination=(IPv4Address("203.0.113.5"), 25),
        version=1,
    )
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=3.0,
        start_tls=False,
        proxy_protocol=config,
    )
    async with client:
        pass

    assert smtpd_handler.proxy_data is not None
    assert smtpd_handler.proxy_data.version == 1
    assert str(smtpd_handler.proxy_data.src_addr) == "192.0.2.1"
    assert smtpd_handler.proxy_data.src_port == 51234
    assert str(smtpd_handler.proxy_data.dst_addr) == "203.0.113.5"
    assert smtpd_handler.proxy_data.dst_port == 25


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_proxy_with_implicit_tls(
    hostname: str,
    smtpd_server_port: int,
    smtpd_handler: RecordingHandler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = ProxyConfig(
        source=(IPv4Address("192.0.2.1"), 51234),
        destination=(IPv4Address("203.0.113.5"), 25),
    )
    loop = asyncio.get_running_loop()
    upgraded_transport: asyncio.BaseTransport | None = None

    async def fake_start_tls(
        transport: asyncio.BaseTransport, *args: Any, **kwargs: Any
    ) -> asyncio.BaseTransport:
        nonlocal upgraded_transport
        upgraded_transport = transport
        return transport

    monkeypatch.setattr(loop, "start_tls", fake_start_tls)

    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=3.0,
        use_tls=True,
        validate_certs=False,
        proxy_protocol=config,
    )
    async with client:
        pass

    assert upgraded_transport is not None, "loop.start_tls was not invoked"
    assert smtpd_handler.proxy_data is not None
    assert smtpd_handler.proxy_data.src_addr == IPv4Address("192.0.2.1")


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_proxy_with_implicit_tls_timeout(
    hostname: str,
    smtpd_server_port: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()

    async def raise_timeout(*args: Any, **kwargs: Any) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr(loop, "start_tls", raise_timeout)

    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=1.0,
        use_tls=True,
        validate_certs=False,
        proxy_protocol=ProxyConfig(
            source=(IPv4Address("192.0.2.1"), 51234),
            destination=(IPv4Address("203.0.113.5"), 25),
        ),
    )
    with pytest.raises(SMTPConnectTimeoutError, match="upgrading"):
        await client.connect()


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_proxy_with_implicit_tls_connection_aborted(
    hostname: str,
    smtpd_server_port: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()

    async def raise_aborted(*args: Any, **kwargs: Any) -> None:
        raise ConnectionAbortedError("aborted")

    monkeypatch.setattr(loop, "start_tls", raise_aborted)

    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=1.0,
        use_tls=True,
        validate_certs=False,
        proxy_protocol=ProxyConfig(
            source=(IPv4Address("192.0.2.1"), 51234),
            destination=(IPv4Address("203.0.113.5"), 25),
        ),
    )
    with pytest.raises(SMTPConnectTimeoutError, match="aborted"):
        await client.connect()


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_proxy_with_implicit_tls_connection_reset(
    hostname: str,
    smtpd_server_port: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()

    async def raise_reset(*args: Any, **kwargs: Any) -> None:
        raise ConnectionResetError("reset")

    monkeypatch.setattr(loop, "start_tls", raise_reset)

    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=1.0,
        use_tls=True,
        validate_certs=False,
        proxy_protocol=ProxyConfig(
            source=(IPv4Address("192.0.2.1"), 51234),
            destination=(IPv4Address("203.0.113.5"), 25),
        ),
    )
    with pytest.raises(SMTPConnectError, match="reset"):
        await client.connect()

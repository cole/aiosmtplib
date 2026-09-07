"""
Tests for the PROXY protocol header encoders and SMTP integration.
"""

import asyncio
import struct
from collections.abc import Callable
from ipaddress import IPv4Address, IPv6Address
from typing import Any

import pytest

import aiosmtplib
from aiosmtplib import (
    SMTP,
    SMTPConnectError,
    SMTPConnectTimeoutError,
    proxy_protocol_header_v1,
    proxy_protocol_header_v2,
    send,
)

from .smtpd import RecordingHandler


V2_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"


def test_v1_tcp4_encode() -> None:
    header = proxy_protocol_header_v1(
        source=(IPv4Address("192.0.2.1"), 51234),
        destination=(IPv4Address("203.0.113.5"), 25),
    )
    assert header == b"PROXY TCP4 192.0.2.1 203.0.113.5 51234 25\r\n"


def test_v1_tcp6_encode() -> None:
    header = proxy_protocol_header_v1(
        source=(IPv6Address("2001:db8::1"), 51234),
        destination=(IPv6Address("2001:db8::5"), 25),
    )
    assert header == b"PROXY TCP6 2001:db8::1 2001:db8::5 51234 25\r\n"


def test_v1_unknown_encode() -> None:
    assert proxy_protocol_header_v1() == b"PROXY UNKNOWN\r\n"


def test_v2_tcp4_encode() -> None:
    header = proxy_protocol_header_v2(
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
    assert header == expected


def test_v2_tcp6_encode() -> None:
    header = proxy_protocol_header_v2(
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
    assert header == expected


def test_unversioned_alias_is_v2() -> None:
    assert aiosmtplib.proxy_protocol_header is proxy_protocol_header_v2


def test_v2_local_encode() -> None:
    expected = V2_SIGNATURE + struct.pack("!BBH", 0x20, 0x00, 0)
    assert proxy_protocol_header_v2() == expected


def test_v2_tlvs_appended_to_payload() -> None:
    tlvs = b"\x01\x00\x03foo"
    header = proxy_protocol_header_v2(
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
    assert header == expected


def test_v2_local_with_tlvs() -> None:
    tlvs = b"\x05\x00\x04abcd"
    expected = V2_SIGNATURE + struct.pack("!BBH", 0x20, 0x00, len(tlvs)) + tlvs
    assert proxy_protocol_header_v2(tlvs=tlvs) == expected


@pytest.mark.parametrize(
    "encoder", [proxy_protocol_header_v1, proxy_protocol_header_v2]
)
def test_mixed_family_rejected(encoder: Callable[..., bytes]) -> None:
    with pytest.raises(ValueError, match="same address family"):
        encoder(
            source=(IPv4Address("192.0.2.1"), 51234),
            destination=(IPv6Address("2001:db8::5"), 25),
        )


@pytest.mark.parametrize(
    "encoder", [proxy_protocol_header_v1, proxy_protocol_header_v2]
)
def test_source_without_destination_rejected(encoder: Callable[..., bytes]) -> None:
    with pytest.raises(ValueError, match="both"):
        encoder(source=(IPv4Address("192.0.2.1"), 51234))


@pytest.mark.parametrize(
    "encoder", [proxy_protocol_header_v1, proxy_protocol_header_v2]
)
def test_destination_without_source_rejected(encoder: Callable[..., bytes]) -> None:
    with pytest.raises(ValueError, match="both"):
        encoder(destination=(IPv4Address("203.0.113.5"), 25))


@pytest.mark.parametrize(
    "encoder", [proxy_protocol_header_v1, proxy_protocol_header_v2]
)
@pytest.mark.parametrize("port", [-1, 65536])
def test_out_of_range_port_rejected(encoder: Callable[..., bytes], port: int) -> None:
    with pytest.raises(ValueError, match="port out of range"):
        encoder(
            source=(IPv4Address("192.0.2.1"), port),
            destination=(IPv4Address("203.0.113.5"), 25),
        )


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_proxy_v2_tcp4(
    hostname: str, smtpd_server_port: int, smtpd_handler: RecordingHandler
) -> None:
    header = proxy_protocol_header_v2(
        source=(IPv4Address("192.0.2.1"), 51234),
        destination=(IPv4Address("203.0.113.5"), 25),
    )
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=3.0,
        start_tls=False,
        proxy_protocol_header=header,
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
    header = proxy_protocol_header_v2(
        source=(IPv6Address("2001:db8::1"), 51234),
        destination=(IPv6Address("2001:db8::5"), 25),
    )
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=3.0,
        start_tls=False,
        proxy_protocol_header=header,
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
        proxy_protocol_header=proxy_protocol_header_v2(),
    )
    async with client:
        pass

    assert smtpd_handler.proxy_data is not None
    assert smtpd_handler.proxy_data.version == 2
    assert smtpd_handler.proxy_data.src_addr is None
    assert smtpd_handler.proxy_data.dst_addr is None


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_proxy_v2_tlvs_passed_through(
    hostname: str, smtpd_server_port: int, smtpd_handler: RecordingHandler
) -> None:
    # PP2_TYPE_UNIQUE_ID (0x05), length 4, value b"abcd"
    tlvs = b"\x05\x00\x04abcd"
    header = proxy_protocol_header_v2(
        source=(IPv4Address("192.0.2.1"), 51234),
        destination=(IPv4Address("203.0.113.5"), 25),
        tlvs=tlvs,
    )
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=3.0,
        start_tls=False,
        proxy_protocol_header=header,
    )
    async with client:
        pass

    assert smtpd_handler.proxy_data is not None
    assert smtpd_handler.proxy_data.src_addr == IPv4Address("192.0.2.1")
    assert smtpd_handler.proxy_data.rest == tlvs
    assert smtpd_handler.proxy_data.tlv is not None
    assert smtpd_handler.proxy_data.tlv.UNIQUE_ID == b"abcd"


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_proxy_v1_tcp4(
    hostname: str, smtpd_server_port: int, smtpd_handler: RecordingHandler
) -> None:
    header = proxy_protocol_header_v1(
        source=(IPv4Address("192.0.2.1"), 51234),
        destination=(IPv4Address("203.0.113.5"), 25),
    )
    client = SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        timeout=3.0,
        start_tls=False,
        proxy_protocol_header=header,
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
    header = proxy_protocol_header_v2(
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
        proxy_protocol_header=header,
    )
    async with client:
        assert client.protocol is not None
        assert client.protocol._over_ssl

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
        proxy_protocol_header=proxy_protocol_header_v2(
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
        proxy_protocol_header=proxy_protocol_header_v2(
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
        proxy_protocol_header=proxy_protocol_header_v2(
            source=(IPv4Address("192.0.2.1"), 51234),
            destination=(IPv4Address("203.0.113.5"), 25),
        ),
    )
    with pytest.raises(SMTPConnectError, match="reset"):
        await client.connect()


@pytest.mark.smtpd_options(proxy_protocol_timeout=3.0)
async def test_send_with_proxy_protocol_header(
    hostname: str,
    smtpd_server_port: int,
    smtpd_handler: RecordingHandler,
    recipient_str: str,
    sender_str: str,
    message_str: str,
) -> None:
    errors, _ = await send(
        message_str,
        hostname=hostname,
        port=smtpd_server_port,
        sender=sender_str,
        recipients=[recipient_str],
        start_tls=False,
        proxy_protocol_header=proxy_protocol_header_v2(
            source=(IPv4Address("192.0.2.1"), 51234),
            destination=(IPv4Address("203.0.113.5"), 25),
        ),
    )

    assert not errors
    assert smtpd_handler.proxy_data is not None
    assert smtpd_handler.proxy_data.src_addr == IPv4Address("192.0.2.1")

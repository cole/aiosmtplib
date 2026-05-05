"""
HAProxy PROXY protocol header configuration and encoding.

Supports protocol versions 1 (text) and 2 (binary), per the spec at
https://www.haproxy.org/download/1.8/doc/proxy-protocol.txt.
"""

import struct
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv6Address
from typing import Literal


__all__ = ("ProxyConfig",)


_V2_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"
_V2_VERSION = 0x20
_V2_CMD_LOCAL = 0x00
_V2_CMD_PROXY = 0x01
_V2_AF_UNSPEC = 0x00
_V2_AF_INET = 0x10
_V2_AF_INET6 = 0x20
_V2_TRANSPORT_STREAM = 0x01


@dataclass(frozen=True)
class ProxyConfig:
    """
    Configuration for sending a HAProxy PROXY protocol header on connect.

    With ``source`` and ``destination`` set, encodes a PROXY command carrying
    the original client and proxy-facing addresses. With both omitted, encodes
    the v2 LOCAL (or v1 UNKNOWN) form for proxy-originated connections such as
    health checks.
    """

    source: tuple[IPv4Address | IPv6Address, int] | None = None
    destination: tuple[IPv4Address | IPv6Address, int] | None = None
    version: Literal[1, 2] = 2
    tlvs: bytes = field(default=b"")

    def __post_init__(self) -> None:
        if self.version not in (1, 2):
            raise ValueError(f"Unsupported PROXY protocol version: {self.version!r}")
        if self.tlvs and self.version == 1:
            raise ValueError("TLVs are only supported in PROXY protocol v2")
        if (self.source is None) != (self.destination is None):
            raise ValueError("source and destination must both be set or both be None")
        if self.source is not None and self.destination is not None:
            if type(self.source[0]) is not type(self.destination[0]):
                raise ValueError(
                    "source and destination must be the same address family"
                )

    def encode(self) -> bytes:
        """
        Encode the configured header to bytes for transmission.
        """
        if self.version == 1:
            return self._encode_v1()
        return self._encode_v2()

    def _encode_v1(self) -> bytes:
        if self.source is None or self.destination is None:
            return b"PROXY UNKNOWN\r\n"
        src_ip, src_port = self.source
        dst_ip, dst_port = self.destination
        proto = "TCP4" if isinstance(src_ip, IPv4Address) else "TCP6"
        return f"PROXY {proto} {src_ip} {dst_ip} {src_port} {dst_port}\r\n".encode(
            "ascii"
        )

    def _encode_v2(self) -> bytes:
        if self.source is None or self.destination is None:
            header = struct.pack(
                "!BBH",
                _V2_VERSION | _V2_CMD_LOCAL,
                _V2_AF_UNSPEC,
                len(self.tlvs),
            )
            return _V2_SIGNATURE + header + self.tlvs

        src_ip, src_port = self.source
        dst_ip, dst_port = self.destination
        af_byte = _V2_AF_INET if isinstance(src_ip, IPv4Address) else _V2_AF_INET6
        body = (
            src_ip.packed
            + dst_ip.packed
            + struct.pack("!HH", src_port, dst_port)
            + self.tlvs
        )
        header = struct.pack(
            "!BBH",
            _V2_VERSION | _V2_CMD_PROXY,
            af_byte | _V2_TRANSPORT_STREAM,
            len(body),
        )
        return _V2_SIGNATURE + header + body

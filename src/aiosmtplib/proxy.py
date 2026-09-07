"""
HAProxy PROXY protocol header encoding.

Supports protocol versions 1 (text) and 2 (binary), per the spec at
https://www.haproxy.org/download/1.8/doc/proxy-protocol.txt.
"""

import struct
from ipaddress import IPv4Address, IPv6Address


__all__ = (
    "proxy_protocol_header",
    "proxy_protocol_header_v1",
    "proxy_protocol_header_v2",
)


_V2_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"
_V2_VERSION = 0x20
_V2_CMD_LOCAL = 0x00
_V2_CMD_PROXY = 0x01
_V2_AF_UNSPEC = 0x00
_V2_AF_INET = 0x10
_V2_AF_INET6 = 0x20
_V2_TRANSPORT_STREAM = 0x01

_AddressType = tuple[IPv4Address | IPv6Address, int]


def _validate_addresses(
    source: _AddressType | None, destination: _AddressType | None
) -> None:
    if (source is None) != (destination is None):
        raise ValueError("source and destination must both be set or both be None")
    if source is not None and destination is not None:
        if type(source[0]) is not type(destination[0]):
            raise ValueError("source and destination must be the same address family")
    for label, address in (("source", source), ("destination", destination)):
        if address is not None and not 0 <= address[1] <= 65535:
            raise ValueError(f"{label} port out of range: {address[1]!r}")


def proxy_protocol_header_v1(
    source: _AddressType | None = None,
    destination: _AddressType | None = None,
) -> bytes:
    """
    Encode a version 1 (text) PROXY protocol header.

    With ``source`` and ``destination`` set, encodes a PROXY line carrying the
    original client and proxy-facing addresses, each an (address, port) tuple.
    With both omitted, encodes the UNKNOWN form for proxy-originated
    connections such as health checks.
    """
    _validate_addresses(source, destination)
    if source is None or destination is None:
        return b"PROXY UNKNOWN\r\n"
    src_ip, src_port = source
    dst_ip, dst_port = destination
    proto = "TCP4" if isinstance(src_ip, IPv4Address) else "TCP6"
    return f"PROXY {proto} {src_ip} {dst_ip} {src_port} {dst_port}\r\n".encode("ascii")


def proxy_protocol_header_v2(
    source: _AddressType | None = None,
    destination: _AddressType | None = None,
    tlvs: bytes = b"",
) -> bytes:
    """
    Encode a version 2 (binary) PROXY protocol header.

    With ``source`` and ``destination`` set, encodes a PROXY command carrying
    the original client and proxy-facing addresses, each an (address, port)
    tuple. With both omitted, encodes the LOCAL command for proxy-originated
    connections such as health checks.

    ``tlvs`` is appended to the header payload verbatim; it must be
    pre-encoded Type-Length-Value bytes per the spec.
    """
    _validate_addresses(source, destination)
    if source is None or destination is None:
        header = struct.pack(
            "!BBH",
            _V2_VERSION | _V2_CMD_LOCAL,
            _V2_AF_UNSPEC,
            len(tlvs),
        )
        return _V2_SIGNATURE + header + tlvs

    src_ip, src_port = source
    dst_ip, dst_port = destination
    af_byte = _V2_AF_INET if isinstance(src_ip, IPv4Address) else _V2_AF_INET6
    body = src_ip.packed + dst_ip.packed + struct.pack("!HH", src_port, dst_port) + tlvs
    header = struct.pack(
        "!BBH",
        _V2_VERSION | _V2_CMD_PROXY,
        af_byte | _V2_TRANSPORT_STREAM,
        len(body),
    )
    return _V2_SIGNATURE + header + body


#: Alias for :func:`proxy_protocol_header_v2`, the recommended version.
proxy_protocol_header = proxy_protocol_header_v2

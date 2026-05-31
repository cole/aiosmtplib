"""
Tests for ESMTP extension parsing.
"""

from aiosmtplib.esmtp import parse_esmtp_extensions


def test_basic_extension_parsing() -> None:
    response = """size.does.matter.af.MIL offers FIFTEEN extensions:
8BITMIME
PIPELINING
DSN
ENHANCEDSTATUSCODES
EXPN
HELP
SAML
SEND
SOML
TURN
XADR
XSTA
ETRN
XGEN
SIZE 51200000
    """
    extensions, auth_types = parse_esmtp_extensions(response)

    assert "size" in extensions
    assert extensions["size"] == "51200000"
    assert "saml" in extensions
    assert "size.does.matter.af.mil" not in extensions
    assert auth_types == []


def test_no_extension_parsing() -> None:
    response = """size.does.matter.af.MIL offers ZERO extensions:
    """
    extensions, auth_types = parse_esmtp_extensions(response)

    assert extensions == {}
    assert auth_types == []


def test_auth_type_parsing() -> None:
    response = """mail.example.com Hello [127.0.0.1]
AUTH FOO BAR
    """
    _, auth_types = parse_esmtp_extensions(response)

    assert "foo" in auth_types
    assert "bar" in auth_types
    assert "bogus" not in auth_types


def test_old_school_auth_type_parsing() -> None:
    response = """mail.example.com Hello [127.0.0.1]
AUTH=PLAIN
    """
    _, auth_types = parse_esmtp_extensions(response)

    assert "plain" in auth_types
    assert "cram-md5" not in auth_types


def test_mixed_auth_type_parsing() -> None:
    response = """mail.example.com Hello [127.0.0.1]
AUTH=PLAIN
AUTH CRAM-MD5
    """
    _, auth_types = parse_esmtp_extensions(response)

    assert "plain" in auth_types
    assert "cram-md5" in auth_types


def test_old_school_multiple_auth_type_parsing() -> None:
    response = """mail.example.com Hello [127.0.0.1]
AUTH=PLAIN LOGIN
    """
    extensions, auth_types = parse_esmtp_extensions(response)

    # Every space-separated method in the advertisement is kept.
    assert auth_types == ["plain", "login"]
    # login() requires the "auth" extension to be registered for old-style
    # advertisements, so supports_extension("auth") stays accurate.
    assert "auth" in extensions


def test_old_school_only_auth_no_junk() -> None:
    response = """mail.example.com Hello [127.0.0.1]
AUTH=CRAM-MD5
    """
    extensions, auth_types = parse_esmtp_extensions(response)

    assert "auth" in extensions
    assert auth_types == ["cram-md5"]


def test_leading_whitespace_extension_parsing() -> None:
    response = "mail.example.com Hello [127.0.0.1]\n   SIZE 1000"
    extensions, _ = parse_esmtp_extensions(response)

    assert extensions["size"] == "1000"


def test_blank_line_no_empty_keyword() -> None:
    response = "mail.example.com Hello [127.0.0.1]\n\n8BITMIME\n"
    extensions, _ = parse_esmtp_extensions(response)

    assert "" not in extensions
    assert "8bitmime" in extensions

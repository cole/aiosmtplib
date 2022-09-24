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
    response = """blah blah blah
AUTH FOO BAR
    """
    extensions, auth_types = parse_esmtp_extensions(response)

    assert "foo" in auth_types
    assert "bar" in auth_types
    assert "bogus" not in auth_types


def test_old_school_auth_type_parsing() -> None:
    response = """blah blah blah
AUTH=PLAIN
    """
    extensions, auth_types = parse_esmtp_extensions(response)

    assert "plain" in auth_types
    assert "cram-md5" not in auth_types


def test_mixed_auth_type_parsing() -> None:
    response = """blah blah blah
AUTH=PLAIN
AUTH CRAM-MD5
    """
    extensions, auth_types = parse_esmtp_extensions(response)

    assert "plain" in auth_types
    assert "cram-md5" in auth_types

"""
Tests for authentication encoding utils.
"""

import base64
import hmac

from hypothesis import given
from hypothesis.strategies import binary, text

from aiosmtplib.auth import (
    auth_crammd5_verify,
    auth_login_encode,
    auth_plain_encode,
    auth_xoauth2_encode,
)


@given(binary(), binary(), binary())
def test_auth_crammd5_verify_bytes(
    username: bytes,
    password: bytes,
    challenge: bytes,
) -> None:
    encoded_challenge = base64.b64encode(challenge)

    # Basically a re-implementation of the function being tested :(
    md5_digest = hmac.new(password, msg=challenge, digestmod="md5")
    verification = username + b" " + md5_digest.hexdigest().encode("ascii")
    encoded_verification = base64.b64encode(verification)

    result = auth_crammd5_verify(username, password, encoded_challenge)

    assert result == encoded_verification


@given(text(), text(), text())
def test_auth_crammd5_verify_str(
    username: str,
    password: str,
    challenge: str,
) -> None:
    username_bytes = username.encode("utf-8")
    password_bytes = password.encode("utf-8")
    challenge_bytes = challenge.encode("utf-8")
    encoded_challenge = base64.b64encode(challenge_bytes)

    # Basically a re-implementation of the function being tested :(
    md5_digest = hmac.new(password_bytes, msg=challenge_bytes, digestmod="md5")
    verification = username_bytes + b" " + md5_digest.hexdigest().encode("ascii")
    encoded_verification = base64.b64encode(verification)

    result = auth_crammd5_verify(username, password, encoded_challenge)

    assert result == encoded_verification


@given(binary(), binary())
def test_auth_plain_encode_bytes(
    username: bytes,
    password: bytes,
) -> None:
    assert auth_plain_encode(username, password) == base64.b64encode(
        b"\0" + username + b"\0" + password
    )


@given(text(), text())
def test_auth_plain_encode_str(
    username: str,
    password: str,
) -> None:
    username_bytes = username.encode("utf-8")
    password_bytes = password.encode("utf-8")

    assert auth_plain_encode(username, password) == base64.b64encode(
        b"\0" + username_bytes + b"\0" + password_bytes
    )


@given(binary(), binary())
def test_auth_login_encode_bytes(
    username: bytes,
    password: bytes,
) -> None:
    assert auth_login_encode(username, password) == (
        base64.b64encode(username),
        base64.b64encode(password),
    )


@given(text(), text())
def test_auth_login_encode_str(
    username: str,
    password: str,
) -> None:
    username_bytes = username.encode("utf-8")
    password_bytes = password.encode("utf-8")

    assert auth_login_encode(username, password) == (
        base64.b64encode(username_bytes),
        base64.b64encode(password_bytes),
    )


@given(binary(), binary())
def test_auth_xoauth2_encode_bytes(
    username: bytes,
    access_token: bytes,
) -> None:
    auth_string = b"user=" + username + b"\x01auth=Bearer " + access_token + b"\x01\x01"
    assert auth_xoauth2_encode(username, access_token) == base64.b64encode(auth_string)


@given(text(), text())
def test_auth_xoauth2_encode_str(
    username: str,
    access_token: str,
) -> None:
    username_bytes = username.encode("utf-8")
    token_bytes = access_token.encode("utf-8")

    auth_string = (
        b"user=" + username_bytes + b"\x01auth=Bearer " + token_bytes + b"\x01\x01"
    )
    assert auth_xoauth2_encode(username, access_token) == base64.b64encode(auth_string)


def test_auth_xoauth2_encode_known_value() -> None:
    """Test against the example from Google's XOAUTH2 documentation."""
    username = "someuser@example.com"
    token = "ya29.vF9dft4qmTc2Nvb3RlckBhdHRhdmlzdGEuY29tCg"

    result = auth_xoauth2_encode(username, token)

    # Decode and verify the structure
    decoded = base64.b64decode(result)
    assert decoded == (
        b"user=someuser@example.com\x01"
        b"auth=Bearer ya29.vF9dft4qmTc2Nvb3RlckBhdHRhdmlzdGEuY29tCg\x01\x01"
    )

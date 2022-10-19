"""
Tests for authentication encoding utils.
"""
import base64
import hmac

from hypothesis import given
from hypothesis.strategies import binary, text

from aiosmtplib.auth import auth_crammd5_verify, auth_login_encode, auth_plain_encode


@given(binary(), binary(), binary())
def test_auth_crammd5_verify_bytes(
    username: bytes,
    password: bytes,
    challenge: bytes,
) -> None:
    encoded_challenge = base64.b64encode(challenge)

    # Basically a re-implementation of the function being tested :(
    md5_digest = hmac.HMAC(password, challenge, "md5")
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
    md5_digest = hmac.HMAC(password_bytes, challenge_bytes, "md5")
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

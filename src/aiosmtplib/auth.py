"""
Authentication related methods.
"""

import base64
import hmac
from typing import Union


__all__ = ("auth_crammd5_verify", "auth_plain_encode", "auth_login_encode")


def _ensure_bytes(value: Union[str, bytes]) -> bytes:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return value

    return value.encode("utf-8")


def auth_crammd5_verify(
    username: Union[str, bytes],
    password: Union[str, bytes],
    challenge: Union[str, bytes],
    /,
) -> bytes:
    """
    CRAM-MD5 auth uses the password as a shared secret to MD5 the server's
    response, and sends the username combined with that (base64 encoded).
    """
    username_bytes = _ensure_bytes(username)
    password_bytes = _ensure_bytes(password)
    decoded_challenge = base64.b64decode(challenge)

    md5_digest = hmac.new(password_bytes, msg=decoded_challenge, digestmod="md5")
    verification = username_bytes + b" " + md5_digest.hexdigest().encode("ascii")
    encoded_verification = base64.b64encode(verification)

    return encoded_verification


def auth_plain_encode(
    username: Union[str, bytes],
    password: Union[str, bytes],
    /,
) -> bytes:
    """
    PLAIN auth base64 encodes the username and password together.
    """
    username_bytes = _ensure_bytes(username)
    password_bytes = _ensure_bytes(password)

    username_and_password = b"\0" + username_bytes + b"\0" + password_bytes
    encoded = base64.b64encode(username_and_password)

    return encoded


def auth_login_encode(
    username: Union[str, bytes],
    password: Union[str, bytes],
    /,
) -> tuple[bytes, bytes]:
    """
    LOGIN auth base64 encodes the username and password and sends them
    in sequence.
    """
    username_bytes = _ensure_bytes(username)
    password_bytes = _ensure_bytes(password)

    encoded_username = base64.b64encode(username_bytes)
    encoded_password = base64.b64encode(password_bytes)

    return encoded_username, encoded_password

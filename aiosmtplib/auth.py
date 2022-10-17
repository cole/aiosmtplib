"""
Authentication related methods.
"""
import base64
import hmac


__all__ = ("crammd5_verify",)


def crammd5_verify(username: bytes, password: bytes, challenge: bytes) -> bytes:
    decoded_challenge = base64.b64decode(challenge)
    md5_digest = hmac.new(password, msg=decoded_challenge, digestmod="md5")
    verification = username + b" " + md5_digest.hexdigest().encode("utf-8")
    encoded_verification = base64.b64encode(verification)

    return encoded_verification

"""
aiosmtplib.auth
===============

Authentication method handling.
Auth methods are implemented as simple functions that return a tuple of
(request_string, callback).

If callback is not None, it should be called with the server response code
and message given in response to the initial request.
"""
import base64
import hmac

from aiosmtplib.typing import AuthReturnType

__all__ = ('AUTH_METHODS', 'auth_crammd5', 'auth_login', 'auth_plain')


def auth_plain(username: str, password: str) -> AuthReturnType:
    """
    PLAIN auth encodes the username and password in one Base64 encoded string.
    No verification message is required.

    Something like:
    220-esmtp.example.com
    AUTH PLAIN dGVzdAB0ZXN0AHRlc3RwYXNz
    235 ok, go ahead (#2.0.0)
    """
    username_and_password = (
        b'\0' + username.encode('utf-8') + b'\0' + password.encode('utf-8'))
    encoded = base64.b64encode(username_and_password).decode('utf-8')
    request = 'PLAIN {}'.format(encoded)

    return request, None


def auth_crammd5(username: str, password: str) -> AuthReturnType:
    """
    CRAM-MD5 auth uses the password as a shared secret to MD5 the server's
    response.

    Something like:
    250 AUTH CRAM-MD5
    auth cram-md5
    334 PDI0NjA5LjEwNDc5MTQwNDZAcG9wbWFpbC5TcGFjZS5OZXQ+
    dGltIGI5MTNhNjAyYzdlZGE3YTQ5NWI0ZTZlNzMzNGQzODkw
    """
    password_bytes = password.encode('utf-8')

    def auth_crammd5_verification(code: int, response: str) -> str:
        challenge = base64.b64decode(response.encode('utf-8'))
        md5_digest = hmac.new(password_bytes, msg=challenge, digestmod='md5')
        verification = '{} {}'.format(username, md5_digest.hexdigest())
        encoded_verification = base64.b64encode(verification.encode('utf-8'))
        response = encoded_verification.decode('utf-8')

        return response

    return 'CRAM-MD5', auth_crammd5_verification


def auth_login(username: str, password: str) -> AuthReturnType:
    """
    LOGIN auth sends the Base64 encoded username and password in sequence.

    Something like:
    250 AUTH LOGIN PLAIN CRAM-MD5
    auth login
    334 VXNlcm5hbWU6
    avlsdkfj
    """
    request_bytes = b'LOGIN ' + base64.b64encode(username.encode('utf-8'))
    request = request_bytes.decode('utf-8')
    verification = base64.b64encode(password.encode('utf-8')).decode('utf-8')

    return request, lambda i, s: verification


# List of authentication methods we support: from preferred to
# less preferred methods. We prefer stronger methods like CRAM-MD5.
AUTH_METHODS = (
    ('cram-md5', auth_crammd5,),
    ('plain', auth_plain,),
    ('login', auth_login,),
)

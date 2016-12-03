"""
Authentication method handling.
We use functions that return a tuple of (request_string, callback).

If callback is not None, it should be called with the server response code
and message to the request.
"""
import base64
import hmac
from typing import Callable, Optional, Tuple

AuthReturnType = Tuple[str, Optional[Callable[[int, str], str]]]
AuthFunctionType = Callable[[str, str], AuthReturnType]


def _b64encode(message: str) -> str:
    bytes_message = message.encode('utf-8')
    encoded = base64.b64encode(bytes_message)
    encoded_str = encoded.decode('utf-8')

    return encoded_str


def _b64decode(message: str) -> str:
    bytes_message = message.encode('utf-8')
    decoded = base64.b64decode(bytes_message)
    decoded_str = decoded.decode('utf-8')

    return decoded_str


def auth_plain(username: str, password: str) -> AuthReturnType:
    """
    PLAIN auth encodes the username and password in one Base64 encoded string.
    No verification message is required.

    Something like:
    220-esmtp.example.com
    AUTH PLAIN dGVzdAB0ZXN0AHRlc3RwYXNz
    235 ok, go ahead (#2.0.0)
    """
    username_and_password = _b64encode('\0{}\0{}'.format(username, password))
    request = 'PLAIN {}'.format(username_and_password)

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
    request = 'CRAM-MD5'
    password_bytes = password.encode('utf-8')

    def auth_crammd5_verification(code: int, response: str) -> str:
        challenge = _b64decode(response).encode('utf-8')  # We want bytes here
        md5_digest = hmac.new(password_bytes, msg=challenge, digestmod='md5')
        verification = '{} {}'.format(username, md5_digest.hexdigest())

        return _b64encode(verification)

    return request, auth_crammd5_verification


def auth_login(username: str, password: str) -> AuthReturnType:
    """
    LOGIN auth sends the Base64 encoded username and password in sequence.

    Something like:
    250 AUTH LOGIN PLAIN CRAM-MD5
    auth login
    334 VXNlcm5hbWU6
    avlsdkfj
    """
    login_request = 'LOGIN {}'.format(_b64encode(username))

    def auth_login_verification(code: int, response: str) -> str:
        verification = _b64encode(password)
        return verification

    return login_request, auth_login_verification


# List of authentication methods we support: from preferred to
# less preferred methods. We prefer stronger methods like CRAM-MD5.
AUTH_METHODS = (
    ('cram-md5', auth_crammd5,),
    ('plain', auth_plain,),
    ('login', auth_login,),
)

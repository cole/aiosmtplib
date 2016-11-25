'''
Authentication method handling.
We use functions that return a tuple of (request_string, callback).

If callback is not None, it should be called with the server response code
and message to the request.
'''
import hmac

from aiosmtplib.textutils import b64_encode, b64_decode


def auth_plain(username, password):
    '''
    PLAIN auth encodes the username and password in one Base64 encoded string.
    No verification message is required.

    Something like:
    220-esmtp.example.com
    AUTH PLAIN dGVzdAB0ZXN0AHRlc3RwYXNz
    235 ok, go ahead (#2.0.0)
    '''
    username_and_password = '\0{}\0{}'.format(username, password)
    request = '{} {}'.format('PLAIN', b64_encode(username_and_password))

    return request, None


def auth_crammd5(username, password):
    '''
    CRAM-MD5 auth uses the password as a shared secret to MD5 the server's
    response.

    Something like:
    250 AUTH CRAM-MD5
    auth cram-md5
    334 PDI0NjA5LjEwNDc5MTQwNDZAcG9wbWFpbC5TcGFjZS5OZXQ+
    dGltIGI5MTNhNjAyYzdlZGE3YTQ5NWI0ZTZlNzMzNGQzODkw
    '''
    request = 'CRAM-MD5'

    def auth_crammd5_verification(code, response):
        challenge = b64_decode(response).encode('utf-8')  # We want bytes here
        md5_digest = hmac.new(
            password.encode('utf-8'), msg=challenge, digestmod='md5')
        verification = '{} {}'.format(username, md5_digest.hexdigest())

        return b64_encode(verification)

    return request, auth_crammd5_verification


def auth_login(username, password):
    '''
    LOGIN auth sends the Base64 encoded username and password in sequence.

    Something like:
    250 AUTH LOGIN PLAIN CRAM-MD5
    auth login
    334 VXNlcm5hbWU6
    avlsdkfj
    '''
    login_request = '{} {}'.format('LOGIN', b64_encode(username))

    def auth_login_verification(code, response):
        verification = b64_encode(password)
        return verification

    return login_request, auth_login_verification


# List of authentication methods we support: from preferred to
# less preferred methods. We prefer stronger methods like CRAM-MD5.
AUTH_METHODS = (
    ('cram-md5', auth_crammd5,),
    ('plain', auth_plain,),
    ('login', auth_login,),
)

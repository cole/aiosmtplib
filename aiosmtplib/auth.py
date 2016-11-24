'''
Authentication method handling.
We use functions that return a tuple of (request_string, callback).

If callback is not None, it should be called with the server response code
and message to the request.
'''
import hmac
from email.base64mime import body_encode, body_decode


def b64_encode(text):
    return body_encode(text.encode('utf-8'), eol='')


def b64_decode(text):
    return body_decode(text).decode('utf-8')


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
        challenge = body_decode(response)  # We want bytes here, not str
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

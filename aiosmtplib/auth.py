'''
Authentication method handling.
We use functions that return a tuple of (request_string, callback).

If callback is not None, it should be called with the server response code
and message to the request.
'''
import base64
import hmac
from email.base64mime import body_encode as encode_base64


def auth_plain(username, password):
    '''
    PLAIN auth encodes the username and password in one Base64 encoded string.
    No verification message is required.

    Something like:
    220-esmtp.example.com
    AUTH PLAIN dGVzdAB0ZXN0AHRlc3RwYXNz
    235 ok, go ahead (#2.0.0)
    '''
    username_and_password = "\0{}\0{}".format(username, password)
    b64_request = encode_base64(username_and_password.encode('ascii'), eol='')
    request = "{} {}".format('PLAIN', b64_request)

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
        challenge = base64.b64decode(response)
        password = password.encode('ascii')
        md5_digest = hmac.new(password, msg=challenge, digestmod='md5')
        verification = '{} {}'.format(username, md5_digest.hexdigest())
        b64_verification = encode_base64(verification.encode('ascii'), eol='')

        return b64_verification

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
    b64_username = encode_base64(username.encode('ascii'), eol='')
    login_request = "{} {}".format('LOGIN', b64_username)

    def auth_login_verification(code, response):
        verification = encode_base64(password.encode('ascii'), eol='')
        return verification

    return login_request, auth_login_verification

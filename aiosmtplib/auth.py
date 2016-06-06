import base64
import hmac
from email.base64mime import body_encode as encode_base64


class BaseAuthMethod:
    extension_name = None

    def encode_request(self, username, password):
        '''
        Generate the initial command for this auth method
        (e.g. 'AUTH username')
        '''
        raise NotImplementedError

    def encode_verification(self, code, response, username, password):
        '''
        Generate the verification string for the auth method, if a 334
        status code is returned.

        None indicates no verification required (AUTH PLAIN).
        '''
        raise NotImplementedError


class AuthCramMD5(BaseAuthMethod):
    '''
    CRAM-MD5 auth uses the password as a shared secret to MD5 the server's
    response.

    Something like:
    250 AUTH CRAM-MD5
    auth cram-md5
    334 PDI0NjA5LjEwNDc5MTQwNDZAcG9wbWFpbC5TcGFjZS5OZXQ+
    dGltIGI5MTNhNjAyYzdlZGE3YTQ5NWI0ZTZlNzMzNGQzODkw
    '''
    extension_name = 'CRAM-MD5'

    def encode_request(self, username, password):
        return self.extension_name

    def encode_verification(self, code, response, username, password):
        challenge = base64.b64decode(response)
        password = password.encode('ascii')
        md5_digest = hmac.new(password, msg=challenge, digestmod='md5')
        plain_response = '{} {}'.format(username, md5_digest.hexdigest())
        b64_response = encode_base64(plain_response.encode('ascii'), eol='')

        return b64_response


class AuthPlain(BaseAuthMethod):
    '''
    PLAIN auth encodes the username and password in one Base64 encoded string.

    Something like:
    220-esmtp.example.com
    AUTH PLAIN dGVzdAB0ZXN0AHRlc3RwYXNz
    235 ok, go ahead (#2.0.0)
    '''
    extension_name = 'PLAIN'

    def encode_request(self, username, password):
        response = "\0{}\0{}".format(username, password)
        b64_response = encode_base64(response.encode('ascii'), eol='')

        return "{} {}".format(self.extension_name, b64_response)

    def encode_verification(self, code, response, username, password):
        return None


class AuthLogin(BaseAuthMethod):
    '''
    LOGIN auth sends the Base64 encoded username and password in sequence.

    Something like:
    250 AUTH LOGIN PLAIN CRAM-MD5
    auth login
    334 VXNlcm5hbWU6
    avlsdkfj
    '''
    extension_name = 'LOGIN'

    def encode_request(self, username, password):
        b64_username = encode_base64(username.encode('ascii'), eol='')

        return "{} {}".format(self.extension_name, b64_username)

    def encode_verification(self, code, response, username, password):
        b64_password = encode_base64(password.encode('ascii'), eol='')

        return b64_password

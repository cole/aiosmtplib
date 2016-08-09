import hmac
import random

import pytest

from aiosmtplib.auth import (
    auth_crammd5, auth_login, auth_plain, b64_encode, b64_decode,
)


USERNAMES_AND_PASSWORDS = [
    ('test', 'test'),
    ('admin124', '$3cr3t$'),
    ('jörg', 'ilöveümläüts'),
]


def crammd5_server_response():
    return ''.join(random.choice('0123456789ABCDEF') for i in range(16))


@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
def test_auth_plain(username, password):
    '''
    Check that auth_plain base64 encodes the username/password given.
    '''
    request_str, callback = auth_plain(username, password)

    assert b64_decode(request_str[6:]) == "\0{}\0{}".format(username, password)
    assert callback is None


@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
def test_auth_login(username, password):
    request_str, callback = auth_login(username, password)
    verification_str = callback(200, 'OK')

    assert b64_decode(request_str[6:]) == username
    assert b64_decode(verification_str) == password


@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
def test_auth_crammd5(username, password):
    request_str, callback = auth_crammd5(username, password)
    server_response = crammd5_server_response()
    verification_str = callback(334, b64_encode(server_response))
    cram_md5 = hmac.new(
        password.encode('utf-8'), msg=server_response.encode('ascii'),
        digestmod='md5')
    expected = b64_encode('{} {}'.format(username, cram_md5.hexdigest()))

    assert request_str == 'CRAM-MD5'
    assert verification_str == expected

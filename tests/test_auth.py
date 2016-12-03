import hmac
import base64
import random

import pytest

from aiosmtplib.auth import auth_crammd5, auth_login, auth_plain


USERNAMES_AND_PASSWORDS = [
    ('test', 'test'),
    ('admin124', '$3cr3t$'),
    ('jörg', 'ilöveümläüts'),
]


def crammd5_server_response():
    return ''.join(random.choice('0123456789ABCDEF') for i in range(16))


@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
def test_auth_plain(username, password):
    """
    Check that auth_plain base64 encodes the username/password given.
    """
    request_str, callback = auth_plain(username, password)

    expected = base64.b64decode(request_str[6:].encode('utf-8'))
    assert expected.decode('utf-8') == '\0{}\0{}'.format(username, password)
    assert callback is None


@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
def test_auth_login(username, password):
    request_str, callback = auth_login(username, password)
    verification_str = callback(200, 'OK')

    expected1 = base64.b64decode(request_str[6:].encode('utf-8'))
    expected2 = base64.b64decode(verification_str.encode('utf-8'))

    assert expected1.decode('utf-8') == username
    assert expected2.decode('utf-8') == password


@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
def test_auth_crammd5(username, password):
    request_str, callback = auth_crammd5(username, password)
    server_response = crammd5_server_response()
    verification_str = callback(
        334, base64.b64encode(server_response.encode('utf-8')).decode('utf-8'))
    cram_md5 = hmac.new(
        password.encode('utf-8'), msg=server_response.encode('ascii'),
        digestmod='md5')

    expected = base64.b64encode(
        username.encode('utf-8') + b' ' + cram_md5.hexdigest().encode('utf-8'))

    assert request_str == 'CRAM-MD5'
    assert verification_str == expected.decode('utf-8')

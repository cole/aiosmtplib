import base64
import random
from collections import deque

import pytest

from aiosmtplib.auth import SMTPAuth, crammd5_verify
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus


USERNAMES_AND_PASSWORDS = [
    ('test', 'test'),
    ('admin124', '$3cr3t$'),
]


class DummySMTPAuth(SMTPAuth):

    transport = None

    def __init__(self, responses=None):
        self.recieved_commands = []
        self.queued_responses = deque(responses or [])

    async def execute_command(self, *args, **kwargs):
        self.recieved_commands.append(b' '.join(args))

        response = self.queued_responses.popleft()

        return SMTPResponse(*response)


def crammd5_server_response():
    return ''.join(random.choice('0123456789ABCDEF') for i in range(16))


@pytest.mark.asyncio(forbid_global_loop=True)
@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
async def test_auth_plain(username, password):
    """
    Check that auth_plain base64 encodes the username/password given.
    """
    authsmtp = DummySMTPAuth(responses=[(SMTPStatus.auth_successful, 'OK')])
    await authsmtp.auth_plain(username, password)

    b64data = base64.b64encode(
        b'\0' + username.encode('ascii') + b'\0' + password.encode('ascii'))
    assert authsmtp.recieved_commands == [b'AUTH PLAIN ' + b64data]


@pytest.mark.asyncio(forbid_global_loop=True)
@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
async def test_auth_login(username, password):
    responses = [
        (SMTPStatus.auth_continue, 'VXNlcm5hbWU6'),
        (SMTPStatus.auth_successful, 'OK'),
    ]
    authsmtp = DummySMTPAuth(responses=responses)
    await authsmtp.auth_login(username, password)

    b64username = base64.b64encode(username.encode('ascii'))
    b64password = base64.b64encode(password.encode('ascii'))

    assert authsmtp.recieved_commands == [
        b'AUTH LOGIN ' + b64username,
        b64password,
    ]


@pytest.mark.asyncio(forbid_global_loop=True)
@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
async def test_auth_crammd5(username, password):
    response_str = base64.b64encode(b'secretteststring').decode('ascii')
    responses = [
        (SMTPStatus.auth_continue, response_str),
        (SMTPStatus.auth_successful, 'OK'),
    ]
    authsmtp = DummySMTPAuth(responses=responses)
    await authsmtp.auth_crammd5(username, password)

    password_bytes = password.encode('ascii')
    username_bytes = username.encode('ascii')
    response_bytes = response_str.encode('ascii')

    expected_command = crammd5_verify(
        username_bytes, password_bytes, response_bytes)

    assert authsmtp.recieved_commands == [
        b'AUTH CRAM-MD5',
        expected_command,
    ]

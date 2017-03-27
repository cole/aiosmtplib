import base64
from collections import deque

import pytest

from aiosmtplib.auth import SMTPAuth, crammd5_verify
from aiosmtplib.errors import SMTPAuthenticationError, SMTPException
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus


USERNAMES_AND_PASSWORDS = [
    ('test', 'test'),
    ('admin124', '$3cr3t$'),
]
SUCCESS_RESPONSE = SMTPResponse(SMTPStatus.auth_successful, 'OK')
FAILURE_RESPONSE = SMTPResponse(SMTPStatus.auth_failed, 'Nope')


class DummySMTPAuth(SMTPAuth):

    transport = None

    def __init__(self, responses=None):
        self.recieved_commands = []
        self.queued_responses = deque(responses or [])
        self.esmtp_extensions = {'auth': ''}
        self.server_auth_methods = ['cram-md5', 'login', 'plain']
        self.supports_esmtp = True

    async def execute_command(self, *args, **kwargs):
        self.recieved_commands.append(b' '.join(args))

        response = self.queued_responses.popleft()

        return SMTPResponse(*response)

    async def _ehlo_or_helo_if_needed(self):
        pass


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_login_without_extension_raises_error():
    authsmtp = DummySMTPAuth()
    authsmtp.esmtp_extensions = {}

    with pytest.raises(SMTPException):
        await authsmtp.login('username', 'bogus')


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_login_unknown_method_raises_error():
    authsmtp = DummySMTPAuth()
    authsmtp.AUTH_METHODS = ('fakeauth',)
    authsmtp.server_auth_methods = ['fakeauth']

    with pytest.raises(RuntimeError):
        await authsmtp.login('username', 'bogus')


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_login_without_method_raises_error():
    authsmtp = DummySMTPAuth()
    authsmtp.server_auth_methods = []

    with pytest.raises(SMTPException):
        await authsmtp.login('username', 'bogus')


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_login_tries_all_methods():
    responses = [
        FAILURE_RESPONSE,  # CRAM-MD5
        FAILURE_RESPONSE,  # PLAIN
        (SMTPStatus.auth_continue, 'VXNlcm5hbWU6'),  # LOGIN continue
        SUCCESS_RESPONSE,  # LOGIN success
    ]
    authsmtp = DummySMTPAuth(responses=responses)
    await authsmtp.login('username', 'thirdtimelucky')


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_login_all_methods_fail_raises_error():
    responses = [
        FAILURE_RESPONSE,  # CRAM-MD5
        FAILURE_RESPONSE,  # PLAIN
        FAILURE_RESPONSE,  # LOGIN
    ]
    authsmtp = DummySMTPAuth(responses=responses)
    with pytest.raises(SMTPAuthenticationError):
        await authsmtp.login('username', 'bogus')


@pytest.mark.asyncio(forbid_global_loop=True)
@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
async def test_auth_plain_success(username, password):
    """
    Check that auth_plain base64 encodes the username/password given.
    """
    authsmtp = DummySMTPAuth(responses=[SUCCESS_RESPONSE])
    await authsmtp.auth_plain(username, password)

    b64data = base64.b64encode(
        b'\0' + username.encode('ascii') + b'\0' + password.encode('ascii'))
    assert authsmtp.recieved_commands == [b'AUTH PLAIN ' + b64data]


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_auth_plain_error():
    authsmtp = DummySMTPAuth(responses=[FAILURE_RESPONSE])

    with pytest.raises(SMTPAuthenticationError):
        await authsmtp.auth_plain('username', 'bogus')


@pytest.mark.asyncio(forbid_global_loop=True)
@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
async def test_auth_login_success(username, password):
    responses = [
        (SMTPStatus.auth_continue, 'VXNlcm5hbWU6'),
        SUCCESS_RESPONSE,
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
async def test_auth_login_error():
    authsmtp = DummySMTPAuth(responses=[FAILURE_RESPONSE])

    with pytest.raises(SMTPAuthenticationError):
        await authsmtp.auth_login('username', 'bogus')


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_auth_plain_continue_error():
    responses = [(SMTPStatus.auth_continue, 'VXNlcm5hbWU6'), FAILURE_RESPONSE]
    authsmtp = DummySMTPAuth(responses=responses)

    with pytest.raises(SMTPAuthenticationError):
        await authsmtp.auth_login('username', 'bogus')


@pytest.mark.asyncio(forbid_global_loop=True)
@pytest.mark.parametrize('username,password', USERNAMES_AND_PASSWORDS)
async def test_auth_crammd5_success(username, password):
    response_str = base64.b64encode(b'secretteststring').decode('ascii')
    responses = [
        (SMTPStatus.auth_continue, response_str),
        SUCCESS_RESPONSE,
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


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_auth_crammd5_initial_error():
    authsmtp = DummySMTPAuth(responses=[FAILURE_RESPONSE])

    with pytest.raises(SMTPAuthenticationError):
        await authsmtp.auth_crammd5('username', 'bogus')


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_auth_crammd5_continue_error():
    responses = [(SMTPStatus.auth_continue, 'VXNlcm5hbWU6'), FAILURE_RESPONSE]
    authsmtp = DummySMTPAuth(responses=responses)

    with pytest.raises(SMTPAuthenticationError):
        await authsmtp.auth_crammd5('username', 'bogus')

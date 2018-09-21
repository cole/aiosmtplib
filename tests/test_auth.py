import base64
from collections import deque

import pytest

from aiosmtplib.auth import SMTPAuth, crammd5_verify
from aiosmtplib.errors import SMTPAuthenticationError, SMTPException
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


USERNAMES_AND_PASSWORDS = [("test", "test"), ("admin124", "$3cr3t$")]
SUCCESS_RESPONSE = SMTPResponse(SMTPStatus.auth_successful, "OK")
FAILURE_RESPONSE = SMTPResponse(SMTPStatus.auth_failed, "Nope")


class DummySMTPAuth(SMTPAuth):

    transport = None

    def __init__(self):
        self.recieved_commands = []
        self.responses = deque()
        self.esmtp_extensions = {"auth": ""}
        self.server_auth_methods = ["cram-md5", "login", "plain"]
        self.supports_esmtp = True

    async def execute_command(self, *args, **kwargs):
        self.recieved_commands.append(b" ".join(args))

        response = self.responses.popleft()

        return SMTPResponse(*response)

    async def _ehlo_or_helo_if_needed(self):
        pass


@pytest.fixture()
def mock_auth(request):
    return DummySMTPAuth()


async def test_login_without_extension_raises_error(mock_auth):
    mock_auth.esmtp_extensions = {}

    with pytest.raises(SMTPException):
        await mock_auth.login("username", "bogus")


async def test_login_unknown_method_raises_error(mock_auth):
    mock_auth.AUTH_METHODS = ("fakeauth",)
    mock_auth.server_auth_methods = ["fakeauth"]

    with pytest.raises(RuntimeError):
        await mock_auth.login("username", "bogus")


async def test_login_without_method_raises_error(mock_auth):
    mock_auth.server_auth_methods = []

    with pytest.raises(SMTPException):
        await mock_auth.login("username", "bogus")


async def test_login_tries_all_methods(mock_auth):
    responses = [
        FAILURE_RESPONSE,  # CRAM-MD5
        FAILURE_RESPONSE,  # PLAIN
        (SMTPStatus.auth_continue, "VXNlcm5hbWU6"),  # LOGIN continue
        SUCCESS_RESPONSE,  # LOGIN success
    ]
    mock_auth.responses.extend(responses)
    await mock_auth.login("username", "thirdtimelucky")


async def test_login_all_methods_fail_raises_error(mock_auth):
    responses = [
        FAILURE_RESPONSE,  # CRAM-MD5
        FAILURE_RESPONSE,  # PLAIN
        FAILURE_RESPONSE,  # LOGIN
    ]
    mock_auth.responses.extend(responses)
    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.login("username", "bogus")


@pytest.mark.parametrize("username,password", USERNAMES_AND_PASSWORDS)
async def test_auth_plain_success(mock_auth, username, password):
    """
    Check that auth_plain base64 encodes the username/password given.
    """
    mock_auth.responses.append(SUCCESS_RESPONSE)
    await mock_auth.auth_plain(username, password)

    b64data = base64.b64encode(
        b"\0" + username.encode("ascii") + b"\0" + password.encode("ascii")
    )
    assert mock_auth.recieved_commands == [b"AUTH PLAIN " + b64data]


async def test_auth_plain_error(mock_auth):
    mock_auth.responses.append(FAILURE_RESPONSE)

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_plain("username", "bogus")


@pytest.mark.parametrize("username,password", USERNAMES_AND_PASSWORDS)
async def test_auth_login_success(mock_auth, username, password):
    continue_response = (SMTPStatus.auth_continue, "VXNlcm5hbWU6")
    mock_auth.responses.extend([continue_response, SUCCESS_RESPONSE])
    await mock_auth.auth_login(username, password)

    b64username = base64.b64encode(username.encode("ascii"))
    b64password = base64.b64encode(password.encode("ascii"))

    assert mock_auth.recieved_commands == [b"AUTH LOGIN " + b64username, b64password]


async def test_auth_login_error(mock_auth):
    mock_auth.responses.append(FAILURE_RESPONSE)
    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_login("username", "bogus")


async def test_auth_plain_continue_error(mock_auth):
    continue_response = (SMTPStatus.auth_continue, "VXNlcm5hbWU6")
    mock_auth.responses.extend([continue_response, FAILURE_RESPONSE])

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_login("username", "bogus")


@pytest.mark.parametrize("username,password", USERNAMES_AND_PASSWORDS)
async def test_auth_crammd5_success(mock_auth, username, password):
    continue_response = (
        SMTPStatus.auth_continue,
        base64.b64encode(b"secretteststring").decode("ascii"),
    )
    mock_auth.responses.extend([continue_response, SUCCESS_RESPONSE])
    await mock_auth.auth_crammd5(username, password)

    password_bytes = password.encode("ascii")
    username_bytes = username.encode("ascii")
    response_bytes = continue_response[1].encode("ascii")

    expected_command = crammd5_verify(username_bytes, password_bytes, response_bytes)

    assert mock_auth.recieved_commands == [b"AUTH CRAM-MD5", expected_command]


async def test_auth_crammd5_initial_error(mock_auth):
    mock_auth.responses.append(FAILURE_RESPONSE)

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_crammd5("username", "bogus")


async def test_auth_crammd5_continue_error(mock_auth):
    continue_response = (SMTPStatus.auth_continue, "VXNlcm5hbWU6")
    mock_auth.responses.extend([continue_response, FAILURE_RESPONSE])

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_crammd5("username", "bogus")

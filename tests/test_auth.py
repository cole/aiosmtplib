import base64
from collections import deque

import pytest

from aiosmtplib.auth import SMTPAuth, crammd5_verify
from aiosmtplib.errors import SMTPAuthenticationError, SMTPException
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus


pytestmark = pytest.mark.asyncio()


SUCCESS_RESPONSE = SMTPResponse(SMTPStatus.auth_successful, "OK")
FAILURE_RESPONSE = SMTPResponse(SMTPStatus.auth_failed, "Nope")


class DummySMTPAuth(SMTPAuth):

    transport = None

    def __init__(self):
        super().__init__()

        self.received_commands = []
        self.responses = deque()
        self.esmtp_extensions = {"auth": ""}
        self.server_auth_methods = ["cram-md5", "login", "plain"]
        self.supports_esmtp = True

    async def execute_command(self, *args, **kwargs):
        self.received_commands.append(b" ".join(args))

        response = self.responses.popleft()

        return SMTPResponse(*response)

    async def _ehlo_or_helo_if_needed(self):
        pass


@pytest.fixture()
def mock_auth(request):
    return DummySMTPAuth()


async def test_login_without_extension_raises_error(mock_auth):
    mock_auth.esmtp_extensions = {}

    with pytest.raises(SMTPException) as excinfo:
        await mock_auth.login("username", "bogus")

    assert "Try connecting via TLS" not in excinfo.value.args[0]


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


@pytest.mark.parametrize(
    "username,password",
    [("test", "test"), ("admin124", "$3cr3t$"), ("føø", "bär€")],
    ids=["test user", "admin user", "utf-8 user"],
)
async def test_auth_plain_success(mock_auth, username, password):
    """
    Check that auth_plain base64 encodes the username/password given.
    """
    mock_auth.responses.append(SUCCESS_RESPONSE)
    await mock_auth.auth_plain(username, password)

    b64data = base64.b64encode(
        b"\0" + username.encode("utf-8") + b"\0" + password.encode("utf-8")
    )
    assert mock_auth.received_commands == [b"AUTH PLAIN " + b64data]


async def test_auth_plain_success_bytes(mock_auth):
    """
    Check that auth_plain base64 encodes the username/password when given as bytes.
    """
    username = "ภาษา".encode("tis-620")
    password = "ไทย".encode("tis-620")
    mock_auth.responses.append(SUCCESS_RESPONSE)
    await mock_auth.auth_plain(username, password)

    b64data = base64.b64encode(b"\0" + username + b"\0" + password)
    assert mock_auth.received_commands == [b"AUTH PLAIN " + b64data]


async def test_auth_plain_error(mock_auth):
    mock_auth.responses.append(FAILURE_RESPONSE)

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_plain("username", "bogus")


@pytest.mark.parametrize(
    "username,password",
    [("test", "test"), ("admin124", "$3cr3t$"), ("føø", "bär€")],
    ids=["test user", "admin user", "utf-8 user"],
)
async def test_auth_login_success(mock_auth, username, password):
    continue_response = (SMTPStatus.auth_continue, "VXNlcm5hbWU6")
    mock_auth.responses.extend([continue_response, SUCCESS_RESPONSE])
    await mock_auth.auth_login(username, password)

    b64username = base64.b64encode(username.encode("utf-8"))
    b64password = base64.b64encode(password.encode("utf-8"))

    assert mock_auth.received_commands == [b"AUTH LOGIN " + b64username, b64password]


async def test_auth_login_success_bytes(mock_auth):
    continue_response = (SMTPStatus.auth_continue, "VXNlcm5hbWU6")
    mock_auth.responses.extend([continue_response, SUCCESS_RESPONSE])

    username = "ภาษา".encode("tis-620")
    password = "ไทย".encode("tis-620")
    await mock_auth.auth_login(username, password)

    b64username = base64.b64encode(username)
    b64password = base64.b64encode(password)

    assert mock_auth.received_commands == [b"AUTH LOGIN " + b64username, b64password]


async def test_auth_login_error(mock_auth):
    mock_auth.responses.append(FAILURE_RESPONSE)
    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_login("username", "bogus")


async def test_auth_plain_continue_error(mock_auth):
    continue_response = (SMTPStatus.auth_continue, "VXNlcm5hbWU6")
    mock_auth.responses.extend([continue_response, FAILURE_RESPONSE])

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_login("username", "bogus")


@pytest.mark.parametrize(
    "username,password",
    [("test", "test"), ("admin124", "$3cr3t$"), ("føø", "bär€")],
    ids=["test user", "admin user", "utf-8 user"],
)
async def test_auth_crammd5_success(mock_auth, username, password):
    continue_response = (
        SMTPStatus.auth_continue,
        base64.b64encode(b"secretteststring").decode("utf-8"),
    )
    mock_auth.responses.extend([continue_response, SUCCESS_RESPONSE])
    await mock_auth.auth_crammd5(username, password)

    password_bytes = password.encode("utf-8")
    username_bytes = username.encode("utf-8")
    response_bytes = continue_response[1].encode("utf-8")

    expected_command = crammd5_verify(username_bytes, password_bytes, response_bytes)

    assert mock_auth.received_commands == [b"AUTH CRAM-MD5", expected_command]


async def test_auth_crammd5_success_bytes(mock_auth):
    continue_response = (
        SMTPStatus.auth_continue,
        base64.b64encode(b"secretteststring").decode("utf-8"),
    )
    mock_auth.responses.extend([continue_response, SUCCESS_RESPONSE])

    username = "ภาษา".encode("tis-620")
    password = "ไทย".encode("tis-620")
    await mock_auth.auth_crammd5(username, password)

    response_bytes = continue_response[1].encode("utf-8")

    expected_command = crammd5_verify(username, password, response_bytes)

    assert mock_auth.received_commands == [b"AUTH CRAM-MD5", expected_command]


async def test_auth_crammd5_initial_error(mock_auth):
    mock_auth.responses.append(FAILURE_RESPONSE)

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_crammd5("username", "bogus")


async def test_auth_crammd5_continue_error(mock_auth):
    continue_response = (SMTPStatus.auth_continue, "VXNlcm5hbWU6")
    mock_auth.responses.extend([continue_response, FAILURE_RESPONSE])

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_crammd5("username", "bogus")


async def test_login_without_starttls_exception(smtp_client, smtpd_server):
    async with smtp_client:
        with pytest.raises(SMTPException) as excinfo:
            await smtp_client.login("test", "test")

        assert "Try connecting via TLS" in excinfo.value.args[0]

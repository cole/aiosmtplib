"""
Tests for auth methods on the SMTP class.
"""
import asyncio
import base64

import pytest

from aiosmtplib import SMTP
from aiosmtplib.auth import auth_crammd5_verify, auth_login_encode, auth_plain_encode
from aiosmtplib.errors import SMTPAuthenticationError, SMTPException
from aiosmtplib.response import SMTPResponse
from aiosmtplib.typing import SMTPStatus

from .auth import DummySMTPAuth


pytestmark = pytest.mark.asyncio()


SUCCESS_RESPONSE = SMTPResponse(SMTPStatus.auth_successful, "OK")
FAILURE_RESPONSE = SMTPResponse(SMTPStatus.auth_failed, "Nope")


async def test_login_without_extension_raises_error(mock_auth: DummySMTPAuth) -> None:
    mock_auth.esmtp_extensions = {}

    with pytest.raises(SMTPException) as excinfo:
        await mock_auth.login("username", "bogus")

    assert "Try connecting via TLS" not in excinfo.value.args[0]


async def test_login_unknown_method_raises_error(mock_auth: DummySMTPAuth) -> None:
    mock_auth.AUTH_METHODS = ("fakeauth",)
    mock_auth.server_auth_methods = ["fakeauth"]

    with pytest.raises(RuntimeError):
        await mock_auth.login("username", "bogus")


async def test_login_without_method_raises_error(mock_auth: DummySMTPAuth) -> None:
    mock_auth.server_auth_methods = []

    with pytest.raises(SMTPException):
        await mock_auth.login("username", "bogus")


async def test_login_tries_all_methods(mock_auth: DummySMTPAuth) -> None:
    responses = [
        FAILURE_RESPONSE,  # CRAM-MD5
        FAILURE_RESPONSE,  # PLAIN
        (SMTPStatus.auth_continue, "VXNlcm5hbWU6"),  # LOGIN continue
        SUCCESS_RESPONSE,  # LOGIN success
    ]
    mock_auth.responses.extend(responses)
    await mock_auth.login("username", "thirdtimelucky")


async def test_login_all_methods_fail_raises_error(mock_auth: DummySMTPAuth) -> None:
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
async def test_auth_plain_success(
    mock_auth: DummySMTPAuth, username: str, password: str
) -> None:
    """
    Check that auth_plain base64 encodes the username/password given.
    """
    mock_auth.responses.append(SUCCESS_RESPONSE)
    await mock_auth.auth_plain(username, password)

    encoded = auth_plain_encode(username, password)
    assert mock_auth.received_commands == [b"AUTH PLAIN " + encoded]


async def test_auth_plain_success_bytes(mock_auth: DummySMTPAuth) -> None:
    """
    Check that auth_plain base64 encodes the username/password when given as bytes.
    """
    username = "ภาษา".encode("tis-620")
    password = "ไทย".encode("tis-620")
    mock_auth.responses.append(SUCCESS_RESPONSE)
    await mock_auth.auth_plain(username, password)

    encoded = auth_plain_encode(username, password)
    assert mock_auth.received_commands == [b"AUTH PLAIN " + encoded]


async def test_auth_plain_error(mock_auth: DummySMTPAuth) -> None:
    mock_auth.responses.append(FAILURE_RESPONSE)

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_plain("username", "bogus")


@pytest.mark.parametrize(
    "username,password",
    [("test", "test"), ("admin124", "$3cr3t$"), ("føø", "bär€")],
    ids=["test user", "admin user", "utf-8 user"],
)
async def test_auth_login_success(
    mock_auth: DummySMTPAuth, username: str, password: str
) -> None:
    continue_response = (SMTPStatus.auth_continue, "VXNlcm5hbWU6")
    mock_auth.responses.extend([continue_response, SUCCESS_RESPONSE])
    await mock_auth.auth_login(username, password)

    encoded_username, encoded_password = auth_login_encode(username, password)

    assert mock_auth.received_commands == [
        b"AUTH LOGIN " + encoded_username,
        encoded_password,
    ]


async def test_auth_login_success_bytes(mock_auth: DummySMTPAuth) -> None:
    continue_response = (SMTPStatus.auth_continue, "VXNlcm5hbWU6")
    mock_auth.responses.extend([continue_response, SUCCESS_RESPONSE])

    username = "ภาษา".encode("tis-620")
    password = "ไทย".encode("tis-620")
    await mock_auth.auth_login(username, password)

    encoded_username, encoded_password = auth_login_encode(username, password)

    assert mock_auth.received_commands == [
        b"AUTH LOGIN " + encoded_username,
        encoded_password,
    ]


async def test_auth_login_error(mock_auth: DummySMTPAuth) -> None:
    mock_auth.responses.append(FAILURE_RESPONSE)
    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_login("username", "bogus")


async def test_auth_plain_continue_error(mock_auth: DummySMTPAuth) -> None:
    continue_response = (SMTPStatus.auth_continue, "VXNlcm5hbWU6")
    mock_auth.responses.extend([continue_response, FAILURE_RESPONSE])

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_login("username", "bogus")


@pytest.mark.parametrize(
    "username,password",
    [("test", "test"), ("admin124", "$3cr3t$"), ("føø", "bär€")],
    ids=["test user", "admin user", "utf-8 user"],
)
async def test_auth_crammd5_success(
    mock_auth: DummySMTPAuth, username: str, password: str
) -> None:
    continue_response = (
        SMTPStatus.auth_continue,
        base64.b64encode(b"secretteststring").decode("utf-8"),
    )
    mock_auth.responses.extend([continue_response, SUCCESS_RESPONSE])
    await mock_auth.auth_crammd5(username, password)

    password_bytes = password.encode("utf-8")
    username_bytes = username.encode("utf-8")
    response_bytes = continue_response[1].encode("utf-8")

    expected_command = auth_crammd5_verify(
        username_bytes, password_bytes, response_bytes
    )

    assert mock_auth.received_commands == [b"AUTH CRAM-MD5", expected_command]


async def test_auth_crammd5_success_bytes(mock_auth: DummySMTPAuth) -> None:
    continue_response = (
        SMTPStatus.auth_continue,
        base64.b64encode(b"secretteststring").decode("utf-8"),
    )
    mock_auth.responses.extend([continue_response, SUCCESS_RESPONSE])

    username = "ภาษา".encode("tis-620")
    password = "ไทย".encode("tis-620")
    await mock_auth.auth_crammd5(username, password)

    response_bytes = continue_response[1].encode("utf-8")

    expected_command = auth_crammd5_verify(username, password, response_bytes)

    assert mock_auth.received_commands == [b"AUTH CRAM-MD5", expected_command]


async def test_auth_crammd5_initial_error(mock_auth: DummySMTPAuth) -> None:
    mock_auth.responses.append(FAILURE_RESPONSE)

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_crammd5("username", "bogus")


async def test_auth_crammd5_continue_error(mock_auth: DummySMTPAuth) -> None:
    continue_response = (SMTPStatus.auth_continue, "VXNlcm5hbWU6")
    mock_auth.responses.extend([continue_response, FAILURE_RESPONSE])

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_crammd5("username", "bogus")


async def test_login_without_starttls_exception(
    smtp_client: SMTP,
    smtpd_server: asyncio.AbstractServer,
    auth_username: str,
    auth_password: str,
) -> None:
    async with smtp_client:
        with pytest.raises(SMTPException) as excinfo:
            await smtp_client.login(auth_username, auth_password)

        assert "Try connecting via TLS" in excinfo.value.args[0]

"""
Tests for auth methods on the SMTP class.
"""

import asyncio
import base64

import pytest

from aiosmtplib import SMTP
from aiosmtplib.auth import (
    auth_crammd5_verify,
    auth_login_encode,
    auth_plain_encode,
    auth_xoauth2_encode,
)
from aiosmtplib.errors import SMTPAuthenticationError, SMTPException
from aiosmtplib.response import SMTPResponse
from aiosmtplib.typing import SMTPStatus

from .auth import DummySMTPAuth


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


@pytest.mark.parametrize(
    "username,token",
    [
        ("test@example.com", "ya29.token123"),
        ("user@gmail.com", "access_token_here"),
        ("føø@example.com", "bär€_token"),
    ],
    ids=["test user", "gmail user", "utf-8 user"],
)
async def test_auth_xoauth2_success(
    mock_auth: DummySMTPAuth, username: str, token: str
) -> None:
    """Check that auth_xoauth2 base64 encodes the username/token correctly."""
    mock_auth.responses.append(SUCCESS_RESPONSE)
    await mock_auth.auth_xoauth2(username, token)

    encoded = auth_xoauth2_encode(username, token)
    assert mock_auth.received_commands == [b"AUTH XOAUTH2 " + encoded]


async def test_auth_xoauth2_success_bytes(mock_auth: DummySMTPAuth) -> None:
    """Check that auth_xoauth2 works with bytes input."""
    username = b"user@example.com"
    token = b"access_token_bytes"
    mock_auth.responses.append(SUCCESS_RESPONSE)
    await mock_auth.auth_xoauth2(username, token)

    encoded = auth_xoauth2_encode(username, token)
    assert mock_auth.received_commands == [b"AUTH XOAUTH2 " + encoded]


async def test_auth_xoauth2_error(mock_auth: DummySMTPAuth) -> None:
    """Check that auth_xoauth2 raises on failure response."""
    mock_auth.responses.append(FAILURE_RESPONSE)

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_xoauth2("user@example.com", "bad_token")


async def test_auth_xoauth2_challenge_error(mock_auth: DummySMTPAuth) -> None:
    """
    Check that auth_xoauth2 handles the error challenge flow.

    On failure, server sends 334 with base64-encoded error JSON,
    client sends empty response, then gets the final 535 error.
    """
    # Server sends error challenge (334), then final error (535)
    challenge_response = (SMTPStatus.auth_continue, "eyJzdGF0dXMiOiI0MDAifQ==")
    mock_auth.responses.extend([challenge_response, FAILURE_RESPONSE])

    with pytest.raises(SMTPAuthenticationError):
        await mock_auth.auth_xoauth2("user@example.com", "expired_token")

    # Verify we sent the initial auth and then empty response
    encoded = auth_xoauth2_encode("user@example.com", "expired_token")
    assert mock_auth.received_commands == [b"AUTH XOAUTH2 " + encoded, b""]


async def test_maybe_login_with_oauth_token_generator(mock_auth: DummySMTPAuth) -> None:
    """Test that _maybe_login_on_connect uses oauth_token_generator when provided."""
    mock_auth.server_auth_methods = ["xoauth2", "plain", "login"]
    mock_auth._login_username = "user@example.com"

    async def get_token() -> str:
        return "test_oauth_token"

    mock_auth._oauth_token_generator = get_token
    mock_auth.responses.append(SUCCESS_RESPONSE)

    await mock_auth._maybe_login_on_connect()

    encoded = auth_xoauth2_encode("user@example.com", "test_oauth_token")
    assert mock_auth.received_commands == [b"AUTH XOAUTH2 " + encoded]


async def test_auth_crammd5_passes_timeout(mock_auth: DummySMTPAuth) -> None:
    """
    Test that auth_crammd5 passes timeout to the verification command.

    Both execute_command calls in auth_crammd5 should receive the timeout parameter.
    """
    continue_response = (
        SMTPStatus.auth_continue,
        base64.b64encode(b"challenge").decode("utf-8"),
    )
    mock_auth.responses.extend([continue_response, SUCCESS_RESPONSE])
    await mock_auth.auth_crammd5("user", "pass", timeout=5.0)

    # Both commands should have received the timeout
    assert len(mock_auth.received_kwargs) == 2
    assert mock_auth.received_kwargs[0].get("timeout") == 5.0
    assert mock_auth.received_kwargs[1].get("timeout") == 5.0

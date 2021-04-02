"""
Authentication methods.
"""
import base64
import hmac
from typing import List, Optional, Union

from .default import Default, _default
from .errors import SMTPAuthenticationError, SMTPException
from .esmtp import ESMTP
from .response import SMTPResponse
from .status import SMTPStatus


__all__ = ("SMTPAuth", "crammd5_verify")


def crammd5_verify(username: bytes, password: bytes, challenge: bytes) -> bytes:
    decoded_challenge = base64.b64decode(challenge)
    md5_digest = hmac.new(password, msg=decoded_challenge, digestmod="md5")
    verification = username + b" " + md5_digest.hexdigest().encode("utf-8")
    encoded_verification = base64.b64encode(verification)

    return encoded_verification


class SMTPAuth(ESMTP):
    """
    Handles ESMTP Authentication support.

    CRAM-MD5, PLAIN, and LOGIN auth methods are supported.
    """

    AUTH_METHODS = ("cram-md5", "plain", "login")  # Preferred methods first

    @property
    def supported_auth_methods(self) -> List[str]:
        """
        Get all AUTH methods supported by the both server and by us.
        """
        return [auth for auth in self.AUTH_METHODS if auth in self.server_auth_methods]

    async def login(
        self,
        username: Union[str, bytes],
        password: Union[str, bytes],
        timeout: Optional[Union[float, Default]] = _default,
    ) -> SMTPResponse:
        """
        Tries to login with supported auth methods.

        Some servers advertise authentication methods they don't really
        support, so if authentication fails, we continue until we've tried
        all methods.
        """
        await self._ehlo_or_helo_if_needed()

        if not self.supports_extension("auth"):
            if self.is_connected and self.get_transport_info("sslcontext") is None:
                raise SMTPException(
                    "The SMTP AUTH extension is not supported by this server. Try "
                    "connecting via TLS (or STARTTLS)."
                )
            raise SMTPException(
                "The SMTP AUTH extension is not supported by this server."
            )

        response = None  # type: Optional[SMTPResponse]
        exception = None  # type: Optional[SMTPAuthenticationError]
        for auth_name in self.supported_auth_methods:
            method_name = "auth_{}".format(auth_name.replace("-", ""))
            try:
                auth_method = getattr(self, method_name)
            except AttributeError:
                raise RuntimeError(
                    "Missing handler for auth method {}".format(auth_name)
                )
            try:
                response = await auth_method(username, password, timeout=timeout)
            except SMTPAuthenticationError as exc:
                exception = exc
            else:
                # No exception means we're good
                break

        if response is None:
            raise exception or SMTPException("No suitable authentication method found.")

        return response

    async def auth_crammd5(
        self,
        username: Union[str, bytes],
        password: Union[str, bytes],
        timeout: Optional[Union[float, Default]] = _default,
    ) -> SMTPResponse:
        """
        CRAM-MD5 auth uses the password as a shared secret to MD5 the server's
        response.

        Example::

            250 AUTH CRAM-MD5
            auth cram-md5
            334 PDI0NjA5LjEwNDc5MTQwNDZAcG9wbWFpbC5TcGFjZS5OZXQ+
            dGltIGI5MTNhNjAyYzdlZGE3YTQ5NWI0ZTZlNzMzNGQzODkw

        """
        initial_response = await self.execute_command(
            b"AUTH", b"CRAM-MD5", timeout=timeout
        )

        if initial_response.code != SMTPStatus.auth_continue:
            raise SMTPAuthenticationError(
                initial_response.code, initial_response.message
            )

        if isinstance(password, bytes):
            password_bytes = password
        else:
            password_bytes = password.encode("utf-8")

        if isinstance(username, bytes):
            username_bytes = username
        else:
            username_bytes = username.encode("utf-8")

        response_bytes = initial_response.message.encode("utf-8")

        verification_bytes = crammd5_verify(
            username_bytes, password_bytes, response_bytes
        )

        response = await self.execute_command(verification_bytes)

        if response.code != SMTPStatus.auth_successful:
            raise SMTPAuthenticationError(response.code, response.message)

        return response

    async def auth_plain(
        self,
        username: Union[str, bytes],
        password: Union[str, bytes],
        timeout: Optional[Union[float, Default]] = _default,
    ) -> SMTPResponse:
        """
        PLAIN auth encodes the username and password in one Base64 encoded
        string. No verification message is required.

        Example::

            220-esmtp.example.com
            AUTH PLAIN dGVzdAB0ZXN0AHRlc3RwYXNz
            235 ok, go ahead (#2.0.0)

        """
        if isinstance(password, bytes):
            password_bytes = password
        else:
            password_bytes = password.encode("utf-8")

        if isinstance(username, bytes):
            username_bytes = username
        else:
            username_bytes = username.encode("utf-8")

        username_and_password = b"\0" + username_bytes + b"\0" + password_bytes
        encoded = base64.b64encode(username_and_password)

        response = await self.execute_command(
            b"AUTH", b"PLAIN", encoded, timeout=timeout
        )

        if response.code != SMTPStatus.auth_successful:
            raise SMTPAuthenticationError(response.code, response.message)

        return response

    async def auth_login(
        self,
        username: Union[str, bytes],
        password: Union[str, bytes],
        timeout: Optional[Union[float, Default]] = _default,
    ) -> SMTPResponse:
        """
        LOGIN auth sends the Base64 encoded username and password in sequence.

        Example::

            250 AUTH LOGIN PLAIN CRAM-MD5
            auth login avlsdkfj
            334 UGFzc3dvcmQ6
            avlsdkfj

        Note that there is an alternate version sends the username
        as a separate command::

            250 AUTH LOGIN PLAIN CRAM-MD5
            auth login
            334 VXNlcm5hbWU6
            avlsdkfj
            334 UGFzc3dvcmQ6
            avlsdkfj

        However, since most servers seem to support both, we send the username
        with the initial request.
        """
        if isinstance(password, bytes):
            password_bytes = password
        else:
            password_bytes = password.encode("utf-8")

        if isinstance(username, bytes):
            username_bytes = username
        else:
            username_bytes = username.encode("utf-8")

        encoded_username = base64.b64encode(username_bytes)
        encoded_password = base64.b64encode(password_bytes)

        initial_response = await self.execute_command(
            b"AUTH", b"LOGIN", encoded_username, timeout=timeout
        )

        if initial_response.code != SMTPStatus.auth_continue:
            raise SMTPAuthenticationError(
                initial_response.code, initial_response.message
            )

        response = await self.execute_command(encoded_password, timeout=timeout)

        if response.code != SMTPStatus.auth_successful:
            raise SMTPAuthenticationError(response.code, response.message)

        return response

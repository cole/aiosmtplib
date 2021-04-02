"""
Main public API.
"""
import email.message
import os
import socket
import ssl
import sys
from typing import Dict, List, Optional, Sequence, Tuple, Union, overload

from .response import SMTPResponse
from .smtp import SMTP


__all__ = ("send",)


if sys.version_info >= (3, 7):
    SocketPathType = Union[str, bytes, os.PathLike]
else:
    SocketPathType = Union[str, bytes]

# flake8: noqa F811

# overloaded matrix is split by:
# * message type (Message, str/bytes)
# * connection type (hostname/socket/socket path)
# * cert info (client_cert/tls_context)


@overload
async def send(
    message: Union[email.message.EmailMessage, email.message.Message],
    sender: Optional[str] = ...,
    recipients: Optional[Union[str, Sequence[str]]] = ...,
    hostname: str = ...,
    port: Optional[int] = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: Optional[str] = ...,
    client_key: Optional[str] = ...,
    tls_context: None = ...,
    cert_bundle: Optional[str] = ...,
    socket_path: None = ...,
    sock: None = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload
async def send(
    message: Union[str, bytes],
    sender: str = ...,
    recipients: Union[str, Sequence[str]] = ...,
    hostname: str = ...,
    port: Optional[int] = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: Optional[str] = ...,
    client_key: Optional[str] = ...,
    tls_context: None = ...,
    cert_bundle: Optional[str] = ...,
    socket_path: None = ...,
    sock: None = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload
async def send(
    message: Union[email.message.EmailMessage, email.message.Message],
    sender: Optional[str] = ...,
    recipients: Optional[Union[str, Sequence[str]]] = ...,
    hostname: str = ...,
    port: Optional[int] = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: None = ...,
    client_key: None = ...,
    tls_context: Optional[ssl.SSLContext] = ...,
    cert_bundle: None = ...,
    socket_path: None = ...,
    sock: None = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload
async def send(
    message: Union[str, bytes],
    sender: str = ...,
    recipients: Union[str, Sequence[str]] = ...,
    hostname: str = ...,
    port: Optional[int] = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: None = ...,
    client_key: None = ...,
    tls_context: Optional[ssl.SSLContext] = ...,
    cert_bundle: None = ...,
    socket_path: None = ...,
    sock: None = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload
async def send(
    message: Union[email.message.EmailMessage, email.message.Message],
    sender: Optional[str] = ...,
    recipients: Optional[Union[str, Sequence[str]]] = ...,
    hostname: None = ...,
    port: None = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: Optional[str] = ...,
    client_key: Optional[str] = ...,
    tls_context: None = ...,
    cert_bundle: Optional[str] = ...,
    socket_path: None = ...,
    sock: socket.socket = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload
async def send(
    message: Union[str, bytes],
    sender: str = ...,
    recipients: Union[str, Sequence[str]] = ...,
    hostname: None = ...,
    port: None = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: Optional[str] = ...,
    client_key: Optional[str] = ...,
    tls_context: None = ...,
    cert_bundle: Optional[str] = ...,
    socket_path: None = ...,
    sock: socket.socket = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload
async def send(
    message: Union[email.message.EmailMessage, email.message.Message],
    sender: Optional[str] = ...,
    recipients: Optional[Union[str, Sequence[str]]] = ...,
    hostname: None = ...,
    port: None = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: None = ...,
    client_key: None = ...,
    tls_context: Optional[ssl.SSLContext] = ...,
    cert_bundle: None = ...,
    socket_path: None = ...,
    sock: socket.socket = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload
async def send(
    message: Union[str, bytes],
    sender: str = ...,
    recipients: Union[str, Sequence[str]] = ...,
    hostname: None = ...,
    port: None = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: None = ...,
    client_key: None = ...,
    tls_context: Optional[ssl.SSLContext] = ...,
    cert_bundle: None = ...,
    socket_path: None = ...,
    sock: socket.socket = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload
async def send(
    message: Union[email.message.EmailMessage, email.message.Message],
    sender: Optional[str] = ...,
    recipients: Optional[Union[str, Sequence[str]]] = ...,
    hostname: None = ...,
    port: None = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: Optional[str] = ...,
    client_key: Optional[str] = ...,
    tls_context: None = ...,
    cert_bundle: Optional[str] = ...,
    socket_path: SocketPathType = ...,
    sock: None = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload
async def send(
    message: Union[str, bytes],
    sender: str = ...,
    recipients: Union[str, Sequence[str]] = ...,
    hostname: None = ...,
    port: None = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: Optional[str] = ...,
    client_key: Optional[str] = ...,
    tls_context: None = ...,
    cert_bundle: Optional[str] = ...,
    socket_path: SocketPathType = ...,
    sock: None = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload
async def send(
    message: Union[email.message.EmailMessage, email.message.Message],
    sender: Optional[str] = ...,
    recipients: Optional[Union[str, Sequence[str]]] = ...,
    hostname: None = ...,
    port: None = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: None = ...,
    client_key: None = ...,
    tls_context: Optional[ssl.SSLContext] = ...,
    cert_bundle: None = ...,
    socket_path: SocketPathType = ...,
    sock: None = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload
async def send(
    message: Union[str, bytes],
    sender: str = ...,
    recipients: Union[str, Sequence[str]] = ...,
    hostname: None = ...,
    port: None = ...,
    username: Optional[Union[str, bytes]] = ...,
    password: Optional[Union[str, bytes]] = ...,
    mail_options: Optional[List[str]] = ...,
    rcpt_options: Optional[List[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: None = ...,
    client_key: None = ...,
    tls_context: Optional[ssl.SSLContext] = ...,
    cert_bundle: None = ...,
    socket_path: SocketPathType = ...,
    sock: None = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


async def send(message, sender=None, recipients=None, **kwargs):
    """
    Send an email message. On await, connects to the SMTP server using the details
    provided, sends the message, then disconnects.

    :param message:  Message text. Either an :py:class:`email.message.EmailMessage`
        object, ``str`` or ``bytes``. If an :py:class:`email.message.EmailMessage`
        object is provided, sender and recipients set in the message headers will be
        used, unless overridden by the respective keyword arguments.
    :keyword sender:  From email address. Not required if an
        :py:class:`email.message.EmailMessage` object is provided for the `message`
        argument.
    :keyword recipients: Recipient email addresses. Not required if an
        :py:class:`email.message.EmailMessage` object is provided for the `message`
        argument.
    :keyword hostname:  Server name (or IP) to connect to. Defaults to "localhost".
    :keyword port: Server port. Defaults ``465`` if ``use_tls`` is ``True``,
        ``587`` if ``start_tls`` is ``True``, or ``25`` otherwise.
    :keyword username:  Username to login as after connect.
    :keyword password:  Password for login after connect.
    :keyword source_address: The hostname of the client. Defaults to the
        result of :py:func:`socket.getfqdn`. Note that this call blocks.
    :keyword timeout: Default timeout value for the connection, in seconds.
        Defaults to 60.
    :keyword use_tls: If True, make the initial connection to the server
        over TLS/SSL. Note that if the server supports STARTTLS only, this
        should be False.
    :keyword start_tls: If True, make the initial connection to the server
        over plaintext, and then upgrade the connection to TLS/SSL. Not
        compatible with use_tls.
    :keyword validate_certs: Determines if server certificates are
        validated. Defaults to True.
    :keyword client_cert: Path to client side certificate, for TLS.
    :keyword client_key: Path to client side key, for TLS.
    :keyword tls_context: An existing :py:class:`ssl.SSLContext`, for TLS.
        Mutually exclusive with ``client_cert``/``client_key``.
    :keyword cert_bundle: Path to certificate bundle, for TLS verification.
    :keyword socket_path: Path to a Unix domain socket. Not compatible with
        hostname or port. Accepts str or bytes, or a pathlike object in 3.7+.
    :keyword sock: An existing, connected socket object. If given, none of
        hostname, port, or socket_path should be provided.

    :raises ValueError: required arguments missing or mutually exclusive options
        provided
    """
    if not isinstance(message, (email.message.EmailMessage, email.message.Message)):
        if not recipients:
            raise ValueError("Recipients must be provided with raw messages.")
        if not sender:
            raise ValueError("Sender must be provided with raw messages.")

    client = SMTP(**kwargs)

    async with client:
        if isinstance(message, (email.message.EmailMessage, email.message.Message)):
            result = await client.send_message(
                message, sender=sender, recipients=recipients
            )
        else:
            result = await client.sendmail(sender, recipients, message)

    return result

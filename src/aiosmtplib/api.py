"""
Main public API.
"""
import ssl
from email.message import Message
from typing import Dict, Iterable, Optional, Tuple, Union, overload

from .compat import get_running_loop
from .connection import DEFAULT_TIMEOUT, SMTP_STARTTLS_PORT
from .response import SMTPResponse
from .smtp import SMTP


__all__ = ("send_message",)


@overload
async def send_message(
    message: Message,
    sender: Optional[str] = None,
    recipients: Optional[Union[str, Iterable[str]]] = None,
    hostname: Optional[str] = None,
    port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    mail_options: Optional[Iterable[str]] = None,
    rcpt_options: Optional[Iterable[str]] = None,
    timeout: Union[float, int, None] = DEFAULT_TIMEOUT,
    source_address: Optional[str] = None,
    use_tls: bool = False,
    start_tls: bool = False,
    validate_certs: bool = True,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
    tls_context: Optional[ssl.SSLContext] = None,
    cert_bundle: Optional[str] = None,
) -> Tuple[Dict[str, SMTPResponse], str]:
    pass


@overload  # NOQA: F811
async def send_message(
    message: Union[str, bytes],
    sender: str = None,
    recipients: Union[str, Iterable[str]] = None,
    hostname: Optional[str] = None,
    port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    mail_options: Optional[Iterable[str]] = None,
    rcpt_options: Optional[Iterable[str]] = None,
    timeout: Union[float, int, None] = DEFAULT_TIMEOUT,
    source_address: Optional[str] = None,
    use_tls: bool = False,
    start_tls: bool = False,
    validate_certs: bool = True,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
    tls_context: Optional[ssl.SSLContext] = None,
    cert_bundle: Optional[str] = None,
) -> Tuple[Dict[str, SMTPResponse], str]:
    pass


async def send_message(  # NOQA: F811
    message,
    sender=None,
    recipients=None,
    username=None,
    password=None,
    start_tls=False,
    port=None,
    use_tls=False,
    **kwargs
):
    """
    Send an email message. On await, connects to the SMTP server using the details
    provided, sends the message, then disconnects.

    :param message:  Message text. Either an :class:``email.message.Message`` object,
        ``str`` or ``bytes``. If a ``Message`` object is provided, sender and
        recipients set in the message headers will be used, unless overridden by
        the respective keyword arguments.
    :keyword sender:  From email address. If a ``Message`` object is provided, this
        argument is not required.
    :keyword recipients: Recipient email addresses. If a ``Message`` object is provided,
        this argument is not required.
    :keyword hostname:  Server name (or IP) to connect to. Defaults to "localhost".
    :keyword port: Server port. Defaults ``465`` if ``use_tls`` is ``True``,
        ``587`` if ``start_tls`` is ``True``, or ``25`` otherwise.
    :keyword username:  Username to login as after connect.
    :keyword password:  Password for login after connect.
    :keyword source_address: The hostname of the client. Defaults to the
        result of :func:`socket.getfqdn`. Note that this call blocks.
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
    :keyword tls_context: An existing :class:`ssl.SSLContext`, for TLS.
        Mutually exclusive with ``client_cert``/``client_key``.
    :keyword cert_bundle: Path to certificate bundle, for TLS verification.

    :raises ValueError: required arguments missing or mutually exclusive options
        provided
    """
    if not isinstance(message, Message):
        if not recipients:
            raise ValueError("Recipients must be provided with raw messages.")
        if not sender:
            raise ValueError("Sender must be provided with raw messages.")

    if start_tls and use_tls:
        raise ValueError("The start_tls and use_tls options are not compatible.")

    if start_tls and port is None:
        port = SMTP_STARTTLS_PORT

    loop = get_running_loop()

    async with SMTP(loop=loop, port=port, use_tls=use_tls, **kwargs) as client:
        if start_tls:
            await client.starttls()
        if username and password:
            await client.login(username, password)

        if isinstance(message, Message):
            result = await client.send_message(
                message, sender=sender, recipients=recipients
            )
        else:
            result = await client.sendmail(sender, recipients, message)

    return result

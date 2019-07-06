"""
Main public API.
"""
import ssl
from email.message import Message
from typing import Dict, Iterable, Optional, Sequence, Tuple, Union, overload

from .response import SMTPResponse
from .smtp import SMTP


__all__ = ("send",)


@overload
async def send(
    message: Message,
    sender: Optional[str] = ...,
    recipients: Optional[Union[str, Sequence[str]]] = ...,
    hostname: Optional[str] = ...,
    port: Optional[int] = ...,
    username: Optional[str] = ...,
    password: Optional[str] = ...,
    mail_options: Optional[Iterable[str]] = ...,
    rcpt_options: Optional[Iterable[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: Optional[str] = ...,
    client_key: Optional[str] = ...,
    tls_context: Optional[ssl.SSLContext] = ...,
    cert_bundle: Optional[str] = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


@overload  # NOQA: F811
async def send(
    message: Union[str, bytes],
    sender: str = ...,
    recipients: Union[str, Sequence[str]] = ...,
    hostname: Optional[str] = ...,
    port: Optional[int] = ...,
    username: Optional[str] = ...,
    password: Optional[str] = ...,
    mail_options: Optional[Iterable[str]] = ...,
    rcpt_options: Optional[Iterable[str]] = ...,
    timeout: Optional[float] = ...,
    source_address: Optional[str] = ...,
    use_tls: bool = ...,
    start_tls: bool = ...,
    validate_certs: bool = ...,
    client_cert: Optional[str] = ...,
    client_key: Optional[str] = ...,
    tls_context: Optional[ssl.SSLContext] = ...,
    cert_bundle: Optional[str] = ...,
) -> Tuple[Dict[str, SMTPResponse], str]:
    ...


async def send(  # NOQA: F811
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

    :param message:  Message text. Either an :py:class:`email.message.Message`
        object, ``str`` or ``bytes``. If an :py:class:`email.message.Message` object is
        provided, sender and recipients set in the message headers will be used, unless
        overridden by the respective keyword arguments.
    :keyword sender:  From email address. Not required if an
        :py:class:`email.message.Message` object is provided for the `message` argument.
    :keyword recipients: Recipient email addresses. Not required if an
        :py:class:`email.message.Message` object is provided for the `message` argument.
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

    :raises ValueError: required arguments missing or mutually exclusive options
        provided
    """
    if not isinstance(message, Message):
        if not recipients:
            raise ValueError("Recipients must be provided with raw messages.")
        if not sender:
            raise ValueError("Sender must be provided with raw messages.")

    client = SMTP(
        port=port,
        username=username,
        password=password,
        use_tls=use_tls,
        start_tls=start_tls,
        **kwargs
    )

    async with client:
        if isinstance(message, Message):
            result = await client.send_message(
                message, sender=sender, recipients=recipients
            )
        else:
            result = await client.sendmail(sender, recipients, message)

    return result

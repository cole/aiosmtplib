"""
Main public API.
"""
import ssl
from email.message import Message
from typing import Iterable, Union

from .compat import get_running_loop
from .default import Default, _default
from .smtp import SMTP


__all__ = ("send_message",)


async def send_message(
    hostname: str,
    message: Union[Message, str, bytes],
    sender: str = None,
    recipients: Union[str, Iterable[str]] = None,
    mail_options: Iterable[str] = None,
    rcpt_options: Iterable[str] = None,
    timeout: Union[float, int, Default] = _default,
    port: int = None,
    source_address: str = None,
    use_tls: bool = False,
    validate_certs: bool = True,
    client_cert: str = None,
    client_key: str = None,
    tls_context: ssl.SSLContext = None,
    cert_bundle: str = None,
):
    """
    Send an email message. On await, connects to the SMTP server using the details
    provided, sends the message, then disconnects.

    :param hostname: Server name (or IP) to connect to
    :param message:  Message text. Either an :class:``email.message.Message`` object,
        ``str`` or ``bytes``. If a ``Message`` object is provided, sender and
        recipients set in the message headers will be used, unless overridden by
        the respective keyword arguments.

    :keyword sender:  From email address. If none, taken from the ``Message``.
    :keyword recipients: Recipient email addresses. If none, taken from the
        ``Message``.
    :keyword mail_options: Options (such as ESMTP 8bitmime) for the MAIL command.
    :keyword rcpt_options: Options (such as DSN commands) for all RCPT commands.

    :keyword port: Server port. Defaults to 25 if ``use_tls`` is
        False, 465 if ``use_tls`` is True.
    :keyword source_address: The hostname of the client. Defaults to the
        result of :func:`socket.getfqdn`. Note that this call blocks.
    :keyword timeout: Default timeout value for the connection, in seconds.
        Defaults to 60.
    :keyword use_tls: If True, make the initial connection to the server
        over TLS/SSL. Note that if the server supports STARTTLS only, this
        should be False.
    :keyword validate_certs: Determines if server certificates are
        validated. Defaults to True.
    :keyword client_cert: Path to client side certificate, for TLS.
    :keyword client_key: Path to client side key, for TLS.
    :keyword tls_context: An existing :class:`ssl.SSLContext`, for TLS.
        Mutually exclusive with ``client_cert``/``client_key``.
    :keyword cert_bundle: Path to certificate bundle, for TLS verification.

    :raises ValueError: mutually exclusive options provided
    """
    loop = get_running_loop()
    client = SMTP(
        loop=loop,
        hostname=hostname,
        port=port,
        source_address=source_address,
        use_tls=use_tls,
        validate_certs=validate_certs,
        client_cert=client_cert,
        client_key=client_key,
        tls_context=tls_context,
        cert_bundle=cert_bundle,
    )

    await client.connect(timeout=timeout)
    await client._ehlo_or_helo_if_needed()

    try:
        if isinstance(message, Message):
            result = await client.send_message(
                message,
                sender=sender,
                recipients=recipients,
                mail_options=mail_options,
                rcpt_options=rcpt_options,
                timeout=timeout,
            )
        else:
            if recipients is None:
                raise ValueError("Recipients must be provided with raw messages.")
            if sender is None:
                raise ValueError("Sender must be provided with raw messages.")

            result = await client.sendmail(
                sender,
                recipients,
                message,
                mail_options=mail_options,
                rcpt_options=rcpt_options,
                timeout=timeout,
            )
    finally:
        await client.quit()

    return result

"""
Main public API.
"""
import email.message
import socket
import ssl
from typing import Dict, Optional, Sequence, Tuple, Union, cast

from .response import SMTPResponse
from .smtp import DEFAULT_TIMEOUT, SMTP
from .typing import SocketPathType


__all__ = ("send",)


async def send(
    message: Union[email.message.EmailMessage, email.message.Message, str, bytes],
    sender: Optional[str] = None,
    recipients: Optional[Union[str, Sequence[str]]] = None,
    mail_options: Optional[Sequence[str]] = None,
    rcpt_options: Optional[Sequence[str]] = None,
    hostname: Optional[str] = "localhost",
    port: Optional[int] = None,
    username: Optional[Union[str, bytes]] = None,
    password: Optional[Union[str, bytes]] = None,
    local_hostname: Optional[str] = None,
    source_address: Optional[Tuple[str, int]] = None,
    timeout: Optional[float] = DEFAULT_TIMEOUT,
    use_tls: bool = False,
    start_tls: Optional[bool] = None,
    validate_certs: bool = True,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
    tls_context: Optional[ssl.SSLContext] = None,
    cert_bundle: Optional[str] = None,
    socket_path: Optional[SocketPathType] = None,
    sock: Optional[socket.socket] = None,
) -> Tuple[Dict[str, SMTPResponse], str]:
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
    :keyword local_hostname: The hostname of the client.  If specified, used as the
        FQDN of the local host in the HELO/EHLO command. Otherwise, the result of
        :func:`socket.getfqdn`. **Note that getfqdn will block the event loop.**
    :keyword source_address: Takes a 2-tuple (host, port) for the socket to bind to
        as its source address before connecting. If the host is '' and port is 0,
        the OS default behavior will be used.
    :keyword timeout: Default timeout value for the connection, in seconds.
        Defaults to 60.
    :keyword use_tls: If True, make the initial connection to the server
        over TLS/SSL. Mutually exclusive with ``start_tls``; if the server uses
        STARTTLS, ``use_tls`` should be ``False``.
    :keyword start_tls: Flag to initiate a STARTTLS upgrade on connect.
        If ``None`` (the default), upgrade will be initiated if supported by the
        server.
        If ``True``, and upgrade will be initiated regardless of server support.
        If ``False``, no upgrade will occur.
        Mutually exclusive with ``use_tls``.
    :keyword validate_certs: Determines if server certificates are
        validated. Defaults to ``True``.
    :keyword client_cert: Path to client side certificate, for TLS.
    :keyword client_key: Path to client side key, for TLS.
    :keyword tls_context: An existing :py:class:`ssl.SSLContext`, for TLS.
        Mutually exclusive with ``client_cert``/``client_key``.
    :keyword cert_bundle: Path to certificate bundle, for TLS verification.
    :keyword socket_path: Path to a Unix domain socket. Not compatible with
        hostname or port. Accepts str, bytes, or a pathlike object.
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

    sender = cast(str, sender)
    recipients = cast(Union[str, Sequence[str]], recipients)

    client = SMTP(
        hostname=hostname,
        port=port,
        local_hostname=local_hostname,
        source_address=source_address,
        timeout=timeout,
        use_tls=use_tls,
        start_tls=start_tls,
        validate_certs=validate_certs,
        client_cert=client_cert,
        client_key=client_key,
        tls_context=tls_context,
        cert_bundle=cert_bundle,
        socket_path=socket_path,
        sock=sock,
        username=username,
        password=password,
    )

    async with client:
        if isinstance(message, (email.message.EmailMessage, email.message.Message)):
            result = await client.send_message(
                message,
                sender=sender,
                recipients=recipients,
                mail_options=mail_options,
                rcpt_options=rcpt_options,
            )
        else:
            result = await client.sendmail(
                sender,
                recipients,
                message,
                mail_options=mail_options,
                rcpt_options=rcpt_options,
            )

    return result

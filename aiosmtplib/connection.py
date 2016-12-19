"""
aiomsmtplib.connection
======================

Handles client connection/disconnection.
"""
import asyncio
import socket
import ssl
from typing import Any, Tuple, Union

from aiosmtplib.errors import (
    SMTPConnectError, SMTPServerDisconnected, SMTPTimeoutError,
)
from aiosmtplib.protocol import SMTPProtocol
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus
from aiosmtplib.typing import (
    OptionalDefaultNumber, OptionalDefaultSSLContext, OptionalDefaultStr,
    OptionalNumber, _default,
)

__all__ = ('SMTPConnection', 'create_connection')

MAX_LINE_LENGTH = 8192
SMTP_PORT = 25
SMTP_TLS_PORT = 465
DEFAULT_TIMEOUT = 60


async def create_connection(
        hostname: str, port: int, tls_context: ssl.SSLContext,
        loop: asyncio.AbstractEventLoop = None,
        timeout: OptionalNumber = None) -> \
        Tuple[SMTPProtocol, asyncio.BaseTransport, SMTPResponse]:
    if loop is None:
        loop = asyncio.get_event_loop()

    reader = asyncio.StreamReader(limit=MAX_LINE_LENGTH, loop=loop)
    protocol = SMTPProtocol(reader, loop=loop)

    connect_future = loop.create_connection(
        lambda: protocol, host=hostname, port=port, ssl=tls_context)
    try:
        transport, _ = await asyncio.wait_for(  # type: ignore
            connect_future, timeout=timeout, loop=loop)
    except (ConnectionRefusedError, OSError) as err:
        raise SMTPConnectError(
            'Error connecting to {host} on port {port}: {err}'.format(
                host=hostname, port=port, err=err))
    except asyncio.TimeoutError as exc:
        raise SMTPTimeoutError(str(exc))

    waiter = protocol.read_response()

    response = None  # type: SMTPResponse
    try:
        response = await asyncio.wait_for(waiter, timeout=timeout, loop=loop)
    except asyncio.TimeoutError as exc:
        raise SMTPTimeoutError(str(exc))

    if response.code != SMTPStatus.ready:
        raise SMTPConnectError(str(response))

    return protocol, transport, response


class SMTPConnection:
    """
    The ``SMTPConnection`` class handles connection/disconnection from the
    SMTP server given.

    Keyword arguments can be provided either on init or when calling the
    ``connect`` method. Note that in both cases these options are saved for
    later use; subsequent calls to ``connect`` with use the same options,
    unless new ones are provided.
    """
    def __init__(
            self, hostname: str = 'localhost', port: int = None,
            source_address: str = None,
            timeout: Union[int, float, None] = DEFAULT_TIMEOUT,
            loop: asyncio.AbstractEventLoop = None,
            use_tls: bool = False, validate_certs: bool = True,
            client_cert: str = None, client_key: str = None,
            tls_context: ssl.SSLContext = None) -> None:
        # Kwarg defaults are provided here, and saved for connect.
        if tls_context and client_cert:
            raise ValueError(
                'Either a TLS context or a certificate/key must be provided')

        self.hostname = hostname
        self.port = port
        self.timeout = timeout
        self.use_tls = use_tls
        self._source_address = source_address
        self.validate_certs = validate_certs
        self.client_cert = client_cert
        self.client_key = client_key
        self.tls_context = tls_context

        self.loop = loop or asyncio.get_event_loop()
        self.protocol = None  # type: SMTPProtocol
        self.transport = None  # type: asyncio.BaseTransport

    def __del__(self):
        """
        Close our transport.
        """
        if self.is_connected:
            self.close()

    @property
    def is_connected(self) -> bool:
        """
        Check if our transport is still connected.
        """
        return bool(self.transport and not self.transport.is_closing())

    @property
    def source_address(self) -> str:
        """
        Get the system hostname to be sent to the SMTP server.
        Simply caches the result of socket.getfqdn.
        """
        if self._source_address is None:
            self._source_address = socket.getfqdn()

        return self._source_address

    async def connect(
            self, hostname: str = None, port: int = None,
            source_address: OptionalDefaultStr = _default,
            timeout: OptionalDefaultNumber = _default,
            loop: asyncio.AbstractEventLoop = None,
            use_tls: bool = None,
            validate_certs: bool = None,
            client_cert: OptionalDefaultStr = _default,
            client_key: OptionalDefaultStr = _default,
            tls_context: OptionalDefaultSSLContext = _default) -> SMTPResponse:
        """
        Open asyncio streams to the server and check response status.
        """
        if hostname is not None:
            self.hostname = hostname
        if port is not None:
            self.port = port
        if loop is not None:
            self.loop = loop
        if use_tls is not None:
            self.use_tls = use_tls
        if validate_certs is not None:
            self.validate_certs = validate_certs

        if timeout is not _default:
            self.timeout = timeout  # type: ignore
        if source_address is not _default:
            self._source_address = source_address  # type: ignore
        if client_cert is not _default:
            self.client_cert = client_cert  # type: ignore
        if client_key is not _default:
            self.client_key = client_key  # type: ignore
        if tls_context is not _default:
            self.tls_context = tls_context  # type: ignore

        if self.tls_context and self.client_cert:
            raise ValueError(
                'Either a TLS context or a certificate/key must be provided')

        if self.port is None:
            if self.use_tls:
                self.port = SMTP_TLS_PORT
            else:
                self.port = SMTP_PORT

        if self.use_tls:
            tls_context = self._get_tls_context()
        else:
            tls_context = None

        self.protocol, self.transport, response = await create_connection(
            self.hostname, self.port, tls_context, loop=self.loop,
            timeout=self.timeout)

        return response

    def _get_tls_context(self) -> ssl.SSLContext:
        """
        Build an SSLContext object from the options we've been given.
        """
        if self.tls_context:
            context = self.tls_context
        else:
            # SERVER_AUTH is what we want for a client side socket
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.check_hostname = bool(self.validate_certs)
            if self.validate_certs:
                context.verify_mode = ssl.CERT_REQUIRED
            else:
                context.verify_mode = ssl.CERT_NONE

            if self.client_cert:
                context.load_cert_chain(
                    self.client_cert, keyfile=self.client_key)

        return context

    def _raise_error_if_disconnected(self) -> None:
        """
        See if we're still connected, and if not, raise
        ``SMTPServerDisconnected``.
        """
        if not self.transport or self.transport.is_closing():
            raise SMTPServerDisconnected('Disconnected from SMTP server')

    def close(self) -> None:
        """
        Closes the connection.
        """
        if self.transport and not self.transport.is_closing():
            self.transport.close()

        self.protocol = None
        self.transport = None

    def get_transport_info(self, key) -> Any:
        """
        Get extra info from the transport.
        Supported keys:
            'peername', 'socket', 'sockname', 'compression', 'cipher',
            'peercert', 'sslcontext', 'ssl_object'
        """
        self._raise_error_if_disconnected()
        assert self.transport is not None

        return self.transport.get_extra_info(key)

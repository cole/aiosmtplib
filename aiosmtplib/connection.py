"""
aiomsmtplib.connection
======================

Handles client connection/disconnection.
"""
import asyncio
import socket
import ssl
from typing import Awaitable, Any, Union  # NOQA

from aiosmtplib.default import Default, _default
from aiosmtplib.errors import (
    SMTPConnectError, SMTPServerDisconnected, SMTPTimeoutError,
)
from aiosmtplib.protocol import SMTPProtocol
from aiosmtplib.response import SMTPResponse
from aiosmtplib.status import SMTPStatus


__all__ = ('SMTPConnection',)

MAX_LINE_LENGTH = 8192
SMTP_PORT = 25
SMTP_TLS_PORT = 465
DEFAULT_TIMEOUT = 60

DefaultNumType = Union[float, int, Default]
DefaultStrType = Union[str, Default]
DefaultSSLContextType = Union[ssl.SSLContext, Default]
NumType = Union[float, int]


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
            self, hostname: str = '', port: int = None,
            source_address: str = None, timeout: NumType = None,
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
        self._connect_lock = asyncio.Lock(loop=self.loop)

    def __del__(self) -> None:
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
            source_address: DefaultStrType = _default,
            timeout: DefaultNumType = _default,
            loop: asyncio.AbstractEventLoop = None,
            use_tls: bool = None, validate_certs: bool = None,
            client_cert: DefaultStrType = _default,
            client_key: DefaultStrType = _default,
            tls_context: DefaultSSLContextType = _default) -> SMTPResponse:
        """
        Open asyncio streams to the server and check response status.
        """
        await self._connect_lock.acquire()

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

        response = await self._create_connection(tls_context)  # type: ignore

        return response

    async def _create_connection(
            self, tls_context: ssl.SSLContext) -> SMTPResponse:
        reader = asyncio.StreamReader(limit=MAX_LINE_LENGTH, loop=self.loop)
        self.protocol = SMTPProtocol(reader, loop=self.loop)

        connect_future = self.loop.create_connection(
            lambda: self.protocol, host=self.hostname, port=self.port,
            ssl=tls_context)
        try:
            self.transport, _ = await asyncio.wait_for(  # type: ignore
                connect_future, timeout=self.timeout, loop=self.loop)
        except (ConnectionRefusedError, OSError) as err:
            raise SMTPConnectError(
                'Error connecting to {host} on port {port}: {err}'.format(
                    host=self.hostname, port=self.port, err=err))
        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError(str(exc))

        waiter = self.protocol.read_response()  # type: Awaitable

        response = None   # type: SMTPResponse
        try:
            response = await asyncio.wait_for(
                waiter, timeout=self.timeout, loop=self.loop)
        except asyncio.TimeoutError as exc:
            raise SMTPTimeoutError(str(exc))

        if response.code != SMTPStatus.ready:
            raise SMTPConnectError(str(response))

        return response

    async def execute_command(
            self, *args: bytes,
            timeout: DefaultNumType = _default) -> SMTPResponse:
        """
        Check that we're connected, if we got a timeout value, and then
        pass the command to the protocol.
        """
        if timeout is _default:
            timeout = self.timeout

        self._raise_error_if_disconnected()

        response = await self.protocol.execute_command(  # type: ignore
            *args, timeout=timeout)

        # If the server is unavailable, be nice and close the connection
        if response.code == SMTPStatus.domain_unavailable:
            self.close()

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
            if self._connect_lock.locked():
                self._connect_lock.release()
            raise SMTPServerDisconnected('Disconnected from SMTP server')

    def close(self) -> None:
        """
        Closes the connection.
        """
        has_active_transport = (
            self.transport is not None and
            not self.transport.is_closing() and
            not self.loop.is_closed()  # type: ignore
        )
        if has_active_transport:
            self.transport.close()

        if self._connect_lock.locked():
            self._connect_lock.release()
        self._reset_server_state()

        self.protocol = None
        self.transport = None

    def get_transport_info(self, key: str) -> Any:
        """
        Get extra info from the transport.
        Supported keys:
            'peername', 'socket', 'sockname', 'compression', 'cipher',
            'peercert', 'sslcontext', 'ssl_object'
        """
        self._raise_error_if_disconnected()
        assert self.transport is not None

        return self.transport.get_extra_info(key)

    def _reset_server_state(self):
        pass

"""
Handles client connection/disconnection.
"""
import asyncio
import socket
import ssl
from typing import Any, Optional, Type, Union  # NOQA

from .default import Default, _default
from .errors import (
    SMTPConnectError,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)
from .protocol import SMTPProtocol
from .response import SMTPResponse
from .status import SMTPStatus


__all__ = ("SMTPConnection",)


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
    Handles connection/disconnection from the SMTP server provided.

    Keyword arguments can be provided either on :meth:`__init__` or when
    calling the :meth:`connect` method. Note that in both cases these options
    are saved for later use; subsequent calls to :meth:`connect` will use the
    same options, unless new ones are provided.
    """

    def __init__(
        self,
        hostname: str = "",
        port: int = None,
        source_address: str = None,
        timeout: NumType = None,
        loop: asyncio.AbstractEventLoop = None,
        use_tls: bool = False,
        validate_certs: bool = True,
        client_cert: str = None,
        client_key: str = None,
        tls_context: ssl.SSLContext = None,
        cert_bundle: str = None,
    ) -> None:
        """
        :keyword hostname:  Server name (or IP) to connect to
        :keyword port: Server port. Defaults to ``25`` if ``use_tls`` is
            ``False``, ``465`` if ``use_tls`` is ``True``.
        :keyword source_address: The hostname of the client. Defaults to the
            result of :func:`socket.getfqdn`. Note that this call blocks.
        :keyword timeout: Default timeout value for the connection, in seconds.
            Defaults to 60.
        :keyword loop: event loop  to run on. If not set, uses
            :func:`asyncio.get_event_loop()`.
        :keyword use_tls: If True, make the initial connection to the server
            over TLS/SSL. Note that if the server supports STARTTLS only, this
            should be False.
        :keyword validate_certs: Determines if server certificates are
            validated. Defaults to True.
        :keyword client_cert: Path to client side certificate, for TLS
            verification.
        :keyword client_key: Path to client side key, for TLS verification.
        :keyword tls_context: An existing :class:`ssl.SSLContext`, for TLS
            verification. Mutually exclusive with ``client_cert``/
            ``client_key``.
        :keyword cert_bundle: Path to certificate bundle, for TLS verification.

        :raises ValueError: mutually exclusive options provided
        """
        self.protocol = None  # type: Optional[SMTPProtocol]
        self.transport = None  # type: Optional[asyncio.BaseTransport]

        if tls_context is not None and client_cert is not None:
            raise ValueError(
                "Either a TLS context or a certificate/key must be provided"
            )

        # Kwarg defaults are provided here, and saved for connect.
        self.hostname = hostname
        self.port = port
        self.timeout = timeout
        self.use_tls = use_tls
        self._source_address = source_address
        self.validate_certs = validate_certs
        self.client_cert = client_cert
        self.client_key = client_key
        self.tls_context = tls_context
        self.cert_bundle = cert_bundle

        self.loop = loop or asyncio.get_event_loop()
        self._connect_lock = asyncio.Lock(loop=self.loop)

    async def __aenter__(self) -> "SMTPConnection":
        if not self.is_connected:
            await self.connect()

        return self

    async def __aexit__(
        self, exc_type: Type[Exception], exc: Exception, traceback: Any
    ) -> None:
        is_connection_error = exc_type in (ConnectionError, SMTPTimeoutError)
        if is_connection_error or not self.is_connected:
            self.close()
        else:
            try:
                await self.quit()
            except (ConnectionError, SMTPResponseException, SMTPTimeoutError):
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
        Simply caches the result of :func:`socket.getfqdn`.
        """
        if self._source_address is None:
            self._source_address = socket.getfqdn()

        return self._source_address

    async def connect(
        self,
        hostname: str = None,
        port: int = None,
        source_address: DefaultStrType = _default,
        timeout: DefaultNumType = _default,
        loop: asyncio.AbstractEventLoop = None,
        use_tls: bool = None,
        validate_certs: bool = None,
        client_cert: DefaultStrType = _default,
        client_key: DefaultStrType = _default,
        tls_context: DefaultSSLContextType = _default,
        cert_bundle: DefaultStrType = _default,
    ) -> SMTPResponse:
        """
        Initialize a connection to the server. Options provided to
        :meth:`.connect` take precedence over those used to initialize the
        class.

        :keyword hostname:  Server name (or IP) to connect to
        :keyword port: Server port. Defaults to 25 if ``use_tls`` is
            False, 465 if ``use_tls`` is True.
        :keyword source_address: The hostname of the client. Defaults to the
            result of :func:`socket.getfqdn`. Note that this call blocks.
        :keyword timeout: Default timeout value for the connection, in seconds.
            Defaults to 60.
        :keyword loop: event loop to run on. If not set, uses
            :func:`asyncio.get_event_loop()`.
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
        await self._connect_lock.acquire()

        if hostname is not None:
            self.hostname = hostname
        if loop is not None:
            self.loop = loop
        if use_tls is not None:
            self.use_tls = use_tls
        if validate_certs is not None:
            self.validate_certs = validate_certs

        if port is not None:
            self.port = port

        if self.port is None:
            self.port = SMTP_TLS_PORT if self.use_tls else SMTP_PORT

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
        if cert_bundle is not _default:
            self.cert_bundle = cert_bundle  # type: ignore

        if self.tls_context is not None and self.client_cert is not None:
            raise ValueError(
                "Either a TLS context or a certificate/key must be provided"
            )

        response = await self._create_connection()

        return response

    async def _create_connection(self) -> SMTPResponse:
        assert self.hostname is not None, "Hostname must be set"
        assert self.port is not None, "Port must be set"

        reader = asyncio.StreamReader(limit=MAX_LINE_LENGTH, loop=self.loop)
        protocol = SMTPProtocol(reader, loop=self.loop)

        tls_context = None  # type: Optional[ssl.SSLContext]
        if self.use_tls:
            tls_context = self._get_tls_context()

        connect_future = self.loop.create_connection(
            lambda: protocol, host=self.hostname, port=self.port, ssl=tls_context
        )
        try:
            transport, _ = await asyncio.wait_for(
                connect_future, timeout=self.timeout, loop=self.loop
            )
        except (ConnectionRefusedError, OSError) as err:
            self.close()
            raise SMTPConnectError(
                "Error connecting to {host} on port {port}: {err}".format(
                    host=self.hostname, port=self.port, err=err
                )
            )
        except asyncio.TimeoutError as exc:
            self.close()
            raise SMTPTimeoutError(str(exc))

        waiter = asyncio.Task(protocol.read_response(), loop=self.loop)

        try:
            response = await asyncio.wait_for(
                waiter, timeout=self.timeout, loop=self.loop
            )
        except asyncio.TimeoutError as exc:
            self.close()
            raise SMTPTimeoutError(str(exc))

        if response.code != SMTPStatus.ready:
            self.close()
            raise SMTPConnectError(str(response))

        self.protocol = protocol
        self.transport = transport

        return response

    async def execute_command(
        self, *args: bytes, timeout: DefaultNumType = _default
    ) -> SMTPResponse:
        """
        Check that we're connected, if we got a timeout value, and then
        pass the command to the protocol.

        :raises SMTPServerDisconnected: connection lost
        """
        if timeout is _default:
            timeout = self.timeout  # type: ignore

        self._raise_error_if_disconnected()

        try:
            response = await self.protocol.execute_command(  # type: ignore
                *args, timeout=timeout
            )
        except SMTPServerDisconnected:
            # On disconnect, clean up the connection.
            self.close()
            raise

        # If the server is unavailable, be nice and close the connection
        if response.code == SMTPStatus.domain_unavailable:
            self.close()

        return response

    async def quit(self, timeout: DefaultNumType = _default) -> SMTPResponse:
        raise NotImplementedError

    def _get_tls_context(self) -> ssl.SSLContext:
        """
        Build an SSLContext object from the options we've been given.
        """
        if self.tls_context is not None:
            context = self.tls_context
        else:
            # SERVER_AUTH is what we want for a client side socket
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.check_hostname = bool(self.validate_certs)
            if self.validate_certs:
                context.verify_mode = ssl.CERT_REQUIRED
            else:
                context.verify_mode = ssl.CERT_NONE

            if self.cert_bundle is not None:
                context.load_verify_locations(cafile=self.cert_bundle)

            if self.client_cert is not None:
                context.load_cert_chain(self.client_cert, keyfile=self.client_key)

        return context

    def _raise_error_if_disconnected(self) -> None:
        """
        See if we're still connected, and if not, raise
        ``SMTPServerDisconnected``.
        """
        if (
            self.transport is None
            or self.protocol is None
            or self.transport.is_closing()
        ):
            self.close()
            raise SMTPServerDisconnected("Disconnected from SMTP server")

    def close(self) -> None:
        """
        Closes the connection.
        """
        if self.transport is not None and not self.transport.is_closing():
            self.transport.close()

        if self._connect_lock.locked():
            self._connect_lock.release()

        self.protocol = None
        self.transport = None

    def get_transport_info(self, key: str) -> Any:
        """
        Get extra info from the transport.
        Supported keys:

            - ``peername``
            - ``socket``
            - ``sockname``
            - ``compression``
            - ``cipher``
            - ``peercert``
            - ``sslcontext``
            - ``sslobject``

        :raises SMTPServerDisconnected: connection lost
        """
        self._raise_error_if_disconnected()

        return self.transport.get_extra_info(key)  # type: ignore

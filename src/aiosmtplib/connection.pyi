import asyncio
import os
import socket
import ssl
import sys
from typing import Any, Optional, Type, Union

from .default import Default
from .protocol import SMTPProtocol
from .response import SMTPResponse

SMTP_PORT = ...  # type: int
SMTP_TLS_PORT = ...  # type: int
SMTP_STARTTLS_PORT = ...  # type: int
DEFAULT_TIMEOUT = ...  # type: int

class SMTPConnection:
    loop = ...  # type: Optional[asyncio.AbstractEventLoop]
    hostname = ...  # type: Optional[str]
    protocol = ...  # type: Optional[SMTPProtocol]
    transport = ...  # type: Optional[asyncio.BaseTransport]
    timeout = ...  # type: Optional[float]

    if sys.version_info[:2] >= (3, 7):
        def __init__(
            self,
            hostname: Optional[str] = ...,
            port: Optional[int] = ...,
            username: Optional[str] = ...,
            password: Optional[str] = ...,
            source_address: Optional[str] = ...,
            timeout: Optional[float] = ...,
            loop: Optional[asyncio.AbstractEventLoop] = ...,
            use_tls: bool = ...,
            start_tls: bool = ...,
            validate_certs: bool = ...,
            client_cert: Optional[str] = ...,
            client_key: Optional[str] = ...,
            tls_context: Optional[ssl.SSLContext] = ...,
            cert_bundle: Optional[str] = ...,
            socket_path: Optional[Union[str, bytes, os.PathLike]] = ...,
            sock: Optional[socket.socket] = ...,
        ) -> None: ...
        def _update_settings_from_kwargs(
            self,
            hostname: Optional[Union[str, Default]] = ...,
            port: Optional[Union[int, Default]] = ...,
            username: Optional[Union[str, Default]] = ...,
            password: Optional[Union[str, Default]] = ...,
            source_address: Optional[Union[str, Default]] = ...,
            timeout: Optional[Union[float, Default]] = ...,
            loop: Optional[Union[asyncio.AbstractEventLoop, Default]] = ...,
            use_tls: Optional[bool] = ...,
            start_tls: Optional[bool] = ...,
            validate_certs: Optional[bool] = ...,
            client_cert: Optional[Union[str, Default]] = ...,
            client_key: Optional[Union[str, Default]] = ...,
            tls_context: Optional[Union[ssl.SSLContext, Default]] = ...,
            cert_bundle: Optional[Union[str, Default]] = ...,
            socket_path: Optional[Union[str, bytes, os.PathLike, Default]] = ...,
            sock: Optional[Union[socket.socket, Default]] = ...,
        ) -> None: ...
    else:
        def __init__(
            self,
            hostname: Optional[str] = ...,
            port: Optional[int] = ...,
            username: Optional[str] = ...,
            password: Optional[str] = ...,
            source_address: Optional[str] = ...,
            timeout: Optional[float] = ...,
            loop: Optional[asyncio.AbstractEventLoop] = ...,
            use_tls: bool = ...,
            start_tls: bool = ...,
            validate_certs: bool = ...,
            client_cert: Optional[str] = ...,
            client_key: Optional[str] = ...,
            tls_context: Optional[ssl.SSLContext] = ...,
            cert_bundle: Optional[str] = ...,
            socket_path: Optional[Union[str, bytes]] = ...,
            sock: Optional[socket.socket] = ...,
        ) -> None: ...
        def _update_settings_from_kwargs(
            self,
            hostname: Optional[Union[str, Default]] = ...,
            port: Optional[Union[int, Default]] = ...,
            username: Optional[Union[str, Default]] = ...,
            password: Optional[Union[str, Default]] = ...,
            source_address: Optional[Union[str, Default]] = ...,
            timeout: Optional[Union[float, Default]] = ...,
            loop: Optional[Union[asyncio.AbstractEventLoop, Default]] = ...,
            use_tls: Optional[bool] = ...,
            start_tls: Optional[bool] = ...,
            validate_certs: Optional[bool] = ...,
            client_cert: Optional[Union[str, Default]] = ...,
            client_key: Optional[Union[str, Default]] = ...,
            tls_context: Optional[Union[ssl.SSLContext, Default]] = ...,
            cert_bundle: Optional[Union[str, Default]] = ...,
            socket_path: Optional[Union[str, bytes, Default]] = ...,
            sock: Optional[Union[socket.socket, Default]] = ...,
        ) -> None: ...
    async def __aenter__(self) -> "SMTPConnection": ...
    async def __aexit__(
        self, exc_type: Type[Exception], exc: Exception, traceback: Any
    ) -> None: ...
    @property
    def is_connected(self) -> bool: ...
    @property
    def source_address(self) -> str: ...
    def _validate_config(self) -> None: ...
    async def connect(self, **kwargs) -> SMTPResponse: ...
    async def _create_connection(self) -> SMTPResponse: ...
    def _connection_lost(self, waiter: asyncio.Future) -> None: ...
    async def execute_command(
        self, *args: bytes, timeout: Optional[Union[float, Default]] = ...
    ) -> SMTPResponse: ...
    async def quit(
        self, timeout: Optional[Union[float, Default]] = ...
    ) -> SMTPResponse: ...
    async def login(
        self,
        username: str,
        password: str,
        timeout: Optional[Union[float, Default]] = ...,
    ) -> SMTPResponse: ...
    async def starttls(
        self,
        server_hostname: Optional[str] = None,
        validate_certs: Optional[bool] = None,
        client_cert: Optional[Union[str, Default]] = ...,
        client_key: Optional[Union[str, Default]] = ...,
        cert_bundle: Optional[Union[str, Default]] = ...,
        tls_context: Optional[Union[ssl.SSLContext, Default]] = ...,
        timeout: Optional[Union[float, Default]] = ...,
    ) -> SMTPResponse: ...
    def _get_tls_context(self) -> ssl.SSLContext: ...
    def close(self) -> None: ...
    def get_transport_info(self, key: str) -> Any: ...

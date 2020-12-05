"""
asyncio compatibility shims.
"""
import asyncio
import ssl
import sys
from asyncio.sslproto import SSLProtocol
from typing import Any, Coroutine, Optional, Set, Tuple, Union


__all__ = (
    "all_tasks",
    "get_running_loop",
    "start_tls",
)


def get_running_loop() -> asyncio.AbstractEventLoop:
    if sys.version_info[:2] >= (3, 7):
        return asyncio.get_running_loop()

    loop = asyncio.get_event_loop()
    if not loop.is_running():
        raise RuntimeError("no running event loop")

    return loop


def all_tasks(
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> Set["asyncio.Task[Any]"]:
    if sys.version_info[:2] >= (3, 7):
        return asyncio.all_tasks(loop=loop)

    return asyncio.Task.all_tasks(loop=loop)


async def start_tls(
    loop: asyncio.AbstractEventLoop,
    transport: asyncio.BaseTransport,
    protocol: asyncio.Protocol,
    sslcontext: ssl.SSLContext,
    server_side: bool = False,
    server_hostname: Optional[str] = None,
    ssl_handshake_timeout: Optional[Union[float, int]] = None,
) -> asyncio.BaseTransport:
    # We use hasattr here, as uvloop also supports start_tls.
    if hasattr(loop, "start_tls"):
        return await loop.start_tls(  # type: ignore
            transport,
            protocol,
            sslcontext,
            server_side=server_side,
            server_hostname=server_hostname,
            ssl_handshake_timeout=ssl_handshake_timeout,
        )

    if not isinstance(transport, asyncio.Transport):
        raise RuntimeError("start_tls requires a transport with pause/resume")

    waiter = loop.create_future()
    ssl_protocol = SSLProtocol(
        loop, protocol, sslcontext, waiter, server_side, server_hostname
    )

    # Pause early so that "ssl_protocol.data_received()" doesn't
    # have a chance to get called before "ssl_protocol.connection_made()".
    transport.pause_reading()

    transport.set_protocol(ssl_protocol)

    conmade_cb = loop.call_soon(ssl_protocol.connection_made, transport)
    resume_cb = loop.call_soon(transport.resume_reading)

    try:
        await asyncio.wait_for(waiter, timeout=ssl_handshake_timeout)
    except Exception:
        transport.close()
        conmade_cb.cancel()
        resume_cb.cancel()
        raise

    return ssl_protocol._app_transport


def create_connection(
    loop: asyncio.AbstractEventLoop, *args: Any, **kwargs: Any
) -> Coroutine[Any, Any, Tuple[asyncio.BaseTransport, asyncio.BaseProtocol]]:
    if sys.version_info[:2] < (3, 7):
        kwargs.pop("ssl_handshake_timeout")

    return loop.create_connection(*args, **kwargs)


def create_unix_connection(
    loop: asyncio.AbstractEventLoop, *args: Any, **kwargs: Any
) -> Coroutine[Any, Any, Tuple[asyncio.BaseTransport, asyncio.BaseProtocol]]:
    if sys.version_info[:2] < (3, 7):
        kwargs.pop("ssl_handshake_timeout")

    return loop.create_unix_connection(*args, **kwargs)

"""
asyncio compatibility shims.
"""
import asyncio
import ssl
import sys
from asyncio.sslproto import SSLProtocol  # type: ignore
from typing import Any, Optional, Union


try:
    import uvloop  # type: ignore
except ImportError:
    uvloop = None


__all__ = (
    "PY36_OR_LATER",
    "PY37_OR_LATER",
    "all_tasks",
    "get_running_loop",
    "open_connection",
    "start_tls",
)


PY36_OR_LATER = sys.version_info[:2] >= (3, 6)
PY37_OR_LATER = sys.version_info[:2] >= (3, 7)


def is_uvloop(loop: Optional[asyncio.AbstractEventLoop] = None):
    if uvloop is None:
        return False
    elif isinstance(loop, uvloop.Loop):
        return True
    else:
        return isinstance(asyncio.get_event_loop_policy(), uvloop.EventLoopPolicy)


class FlowControlMixin(object):
    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        if loop is None:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop
        self._paused = False
        self._drain_waiter = None  # type: Optional[asyncio.Future]
        self._connection_lost = False

    def pause_writing(self):
        self._paused = True

    def resume_writing(self):
        self._paused = False

        waiter = self._drain_waiter
        if waiter is not None:
            self._drain_waiter = None
            if not waiter.done():
                waiter.set_result(None)

    def connection_lost(self, exc: Optional[Exception]):
        self._connection_lost = True
        # Wake up the writer if currently paused.
        if not self._paused:
            return
        waiter = self._drain_waiter
        if waiter is None:
            return
        self._drain_waiter = None
        if waiter.done():
            return
        if exc is None:
            waiter.set_result(None)
        else:
            waiter.set_exception(exc)

    async def _drain_helper(self):
        if self._connection_lost:
            raise ConnectionResetError("Connection lost")
        if not self._paused:
            return
        waiter = self._loop.create_future()
        self._drain_waiter = waiter
        await waiter


class StreamReaderProtocol(FlowControlMixin, asyncio.Protocol):
    """
    This protocol is based on asyncio.StreamReaderProtocol, but the code has
    been copied to avoid references to private attributes.

    Only used on Python 3.5.2.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        super().__init__(loop=loop)

        self._transport = None  # type: Optional[asyncio.BaseTransport]
        self._stream_reader = reader  # type: Optional[asyncio.StreamReader]
        self._stream_writer = None  # type: Optional[asyncio.StreamWriter]
        self._over_ssl = False
        self._closed = self._loop.create_future()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        if self._stream_reader is None:
            raise RuntimeError("Connection made on protocol with no stream reader")
        # We set the _transport directly on the StreamReader, rather than calling
        # set_transport (which will raise an AssertionError on upgrade).
        # This is because on 3.5.2, we can't avoid calling connection_made on
        # upgrade.
        self._transport = transport
        self._stream_reader._transport = transport  # type: ignore
        self._over_ssl = transport.get_extra_info("sslcontext") is not None
        self._stream_writer = asyncio.StreamWriter(
            transport, self, self._stream_reader, self._loop
        )

    def connection_lost(self, exc: Optional[Exception]):
        if self._stream_reader is not None:
            if exc is None:
                self._stream_reader.feed_eof()
            else:
                self._stream_reader.set_exception(exc)
        if not self._closed.done():
            if exc is None:
                self._closed.set_result(None)
            else:
                self._closed.set_exception(exc)
        super().connection_lost(exc)

        self._stream_reader = None
        self._stream_writer = None

    def data_received(self, data: bytes):
        if self._stream_reader is None:
            raise RuntimeError("Data received on protocol with no stream reader")

        self._stream_reader.feed_data(data)

    def eof_received(self):
        if self._stream_reader is None:
            raise RuntimeError("EOF received on protocol with no stream reader")

        self._stream_reader.feed_eof()
        if self._over_ssl:
            # Prevent a warning in SSLProtocol.eof_received:
            # "returning true from eof_received()
            # has no effect when using ssl"
            return False
        return True

    def _get_close_waiter(self, stream: Any):
        return self._closed

    def __del__(self):
        # Prevent reports about unhandled exceptions.
        # Better than self._closed._log_traceback = False hack
        closed = self._closed
        if closed.done() and not closed.cancelled():
            closed.exception()


def get_running_loop() -> asyncio.AbstractEventLoop:
    if PY37_OR_LATER:
        return asyncio.get_running_loop()

    loop = asyncio.get_event_loop()
    if not loop.is_running():
        raise RuntimeError("no running event loop")

    return loop


def all_tasks(loop: asyncio.AbstractEventLoop = None):
    if PY37_OR_LATER:
        return asyncio.all_tasks(loop=loop)

    return asyncio.Task.all_tasks(loop=loop)


async def open_connection(
    host: str,
    port: int,
    loop: asyncio.AbstractEventLoop = None,
    limit: int = 2 ** 16,
    **kwargs
):
    # Using the stock open connection requires start_tls compatiblity
    if PY37_OR_LATER or is_uvloop(loop=loop):
        return await asyncio.open_connection(
            host=host, port=port, loop=loop, limit=limit, **kwargs
        )

    kwargs.pop("ssl_handshake_timeout")

    if loop is None:
        loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader(limit=limit, loop=loop)
    protocol = StreamReaderProtocol(reader, loop=loop)
    transport, _ = await loop.create_connection(  # type: ignore
        lambda: protocol, host, port, **kwargs
    )
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)

    return reader, writer


async def start_tls(
    loop: asyncio.AbstractEventLoop,
    transport: asyncio.BaseTransport,
    protocol: asyncio.Protocol,
    sslcontext: ssl.SSLContext,
    server_side: bool = False,
    server_hostname: Optional[str] = None,
    ssl_handshake_timeout: Optional[Union[float, int]] = None,
) -> asyncio.Transport:
    if PY37_OR_LATER or is_uvloop(loop=loop):
        return await loop.start_tls(  # type: ignore
            transport,
            protocol,
            sslcontext,
            server_side=server_side,
            server_hostname=server_hostname,
            ssl_handshake_timeout=ssl_handshake_timeout,
        )

    waiter = loop.create_future()
    ssl_protocol = SSLProtocol(
        loop, protocol, sslcontext, waiter, server_side, server_hostname
    )

    # Pause early so that "ssl_protocol.data_received()" doesn't
    # have a chance to get called before "ssl_protocol.connection_made()".
    transport.pause_reading()  # type: ignore

    # Use set_protocol if we can
    if hasattr(transport, "set_protocol"):
        transport.set_protocol(ssl_protocol)  # type: ignore
    else:
        transport._protocol = ssl_protocol  # type: ignore

    conmade_cb = loop.call_soon(ssl_protocol.connection_made, transport)
    resume_cb = loop.call_soon(transport.resume_reading)  # type: ignore

    try:
        await asyncio.wait_for(waiter, timeout=ssl_handshake_timeout)
    except Exception:
        transport.close()
        conmade_cb.cancel()
        resume_cb.cancel()
        raise

    return ssl_protocol._app_transport

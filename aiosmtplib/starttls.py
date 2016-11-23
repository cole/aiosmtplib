'''
STARTTLS implementation taken from Yury Selivanov
(http://bugs.python.org/issue23749).

This is a fragile implementation as it depends on asyncio internals that
may (will!) change. Hopefully, we can remove it in future.
'''
import ssl
import selectors
import asyncio
import asyncio.selector_events
import asyncio.sslproto
from asyncio.log import logger


class SSLProtocol(asyncio.sslproto.SSLProtocol):

    def __init__(self, *args, call_connection_made=True, **kwargs):
        super().__init__(*args, **kwargs)
        self._call_connection_made = call_connection_made

    def _on_handshake_complete(self, handshake_exc):
        self._in_handshake = False

        sslobj = self._sslpipe.ssl_object
        try:
            if handshake_exc is not None:
                raise handshake_exc

            peercert = sslobj.getpeercert()
        except BaseException as exc:
            if self._loop.get_debug():
                if isinstance(exc, ssl.CertificateError):
                    logger.warning("%r: SSL handshake failed "
                                   "on verifying the certificate",
                                   self, exc_info=True)
                else:
                    logger.warning("%r: SSL handshake failed",
                                   self, exc_info=True)
            self._transport.close()
            if isinstance(exc, Exception):
                self._wakeup_waiter(exc)
                return
            else:
                raise

        if self._loop.get_debug():
            dt = self._loop.time() - self._handshake_start_time
            logger.debug("%r: SSL handshake took %.1f ms", self, dt * 1e3)

        # Add extra info that becomes available after handshake.
        self._extra.update(peercert=peercert,
                           cipher=sslobj.cipher(),
                           compression=sslobj.compression(),
                           ssl_object=sslobj,
                           )
        if self._call_connection_made:
            self._app_protocol.connection_made(self._app_transport)
        self._wakeup_waiter()
        self._session_established = True
        # In case transport.write() was already called. Don't call
        # immediately _process_write_backlog(), but schedule it:
        # _on_handshake_complete() can be called indirectly from
        # _process_write_backlog(), and _process_write_backlog() is not
        # reentrant.
        self._loop.call_soon(self._process_write_backlog)


class TransportMixin(asyncio.Transport):

    def start_tls(self, sslcontext, *, server_side=False, server_hostname=None,
                  waiter=None):

        app_protocol = self._protocol
        ssl_protocol = SSLProtocol(
            loop=self._loop, app_protocol=app_protocol,
            sslcontext=sslcontext, waiter=waiter, server_side=server_side,
            server_hostname=server_hostname, call_connection_made=False)

        self._protocol = ssl_protocol
        ssl_protocol.connection_made(self)
        return ssl_protocol._app_transport


class _SelectorSocketStartTLSTransport(
        asyncio.selector_events._SelectorSocketTransport, TransportMixin):
    pass


class StartTLSSelectorEventLoop(asyncio.SelectorEventLoop):

    def _make_socket_transport(self, sock, protocol, waiter=None, *,
                               extra=None, server=None):
        return _SelectorSocketStartTLSTransport(
            self, sock, protocol, waiter, extra, server)


class StreamReaderProtocol(asyncio.StreamReaderProtocol):

    def start_tls(self, sslcontext, *, server_side=False,
                  server_hostname=None, waiter=None):

        transport = self._stream_reader._transport
        new_transport = transport.start_tls(
            sslcontext, server_side=server_side,
            server_hostname=server_hostname, waiter=waiter)

        self._stream_reader._transport = new_transport
        if self._stream_writer is not None:
            self._stream_writer._transport = new_transport

        return new_transport


class StreamWriter(asyncio.StreamWriter):

    async def start_tls(self, sslcontext, *, server_side=False,
                        server_hostname=None):

        if not asyncio.sslproto._is_sslproto_available():
            # Python 3.5 or greater is required
            raise NotImplementedError

        await self.drain()

        waiter = asyncio.Future(loop=self._loop)

        new_transport = self._protocol.start_tls(
            sslcontext, server_side=server_side,
            server_hostname=server_hostname, waiter=waiter)

        self._transport = new_transport

        await waiter


# Globally install our custom event loop
asyncio.set_event_loop(StartTLSSelectorEventLoop(selectors.SelectSelector()))

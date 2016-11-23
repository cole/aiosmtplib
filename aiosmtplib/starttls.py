import asyncio
import asyncio.selector_events
import asyncio.sslproto


class SMTPProtocol(asyncio.StreamReaderProtocol):
    _transport = None

    def connection_made(self, transport):
        if (self._transport is not None
                and isinstance(transport,
                               asyncio.sslproto._SSLProtocolTransport)):
            # It is STARTTLS connection over normal connection
            self._stream_reader._transport = transport
            self._over_ssl = True
        else:
            super().connection_made(transport)
        self._transport = transport

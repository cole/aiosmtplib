.. py:currentmodule:: aiosmtplib

Proxy Support
=============


SOCKS Proxies
~~~~~~~~~~~~~

You can use the `python-socks`_ library to connect to a SOCKS proxy.

Create a socket using the ``proxy.connect`` method, and pass it as the ``sock``
argument to the :func:`send` coroutine or :py:class:`SMTP` class.

.. code-block:: python

    import ssl
    import asyncio
    import aiosmtplib
    from python_socks.async_.asyncio import Proxy

    hello_message = """To: somebody@example.com
        From: root@localhost
        Subject: Hello World!

        Sent via aiosmtplib
    """

    async def send_via_proxy(message):
        proxy = Proxy.from_url('socks5://user:password@127.0.0.1:1080')

        # `proxy.connect` returns a socket in non-blocking mode
        sock = await proxy.connect(dest_host='example.com', dest_port=443)


        # Use the socket with aiosmtplib
        await aiosmtplib.send(
            message,
            sender="root@localhost",
            recipients=["somebody@example.com"],
            sock=sock,
        )

    asyncio.run(send_via_proxy(hello_message))


.. _python-socks: https://pypi.org/project/python-socks/


HAProxy PROXY Protocol
~~~~~~~~~~~~~~~~~~~~~~

If your SMTP server sits behind a proxy that expects the `HAProxy PROXY
protocol`_ (e.g. HAProxy itself, or Postfix with ``postscreen_upstream_proxy_protocol``),
pass an encoded header as the ``proxy_protocol_header`` argument to the
:func:`send` coroutine or :py:class:`SMTP` class. The header is sent
immediately on connect, before the TLS handshake (if any) and before any SMTP
data.

Use :func:`proxy_protocol_header_v1` or :func:`proxy_protocol_header_v2` to
encode a version 1 (text) or version 2 (binary) header respectively; any
pre-encoded ``bytes`` value is also accepted. :func:`proxy_protocol_header`
is an alias for the v2 encoder, the recommended version.

.. code-block:: python

    import asyncio
    from ipaddress import IPv4Address

    import aiosmtplib

    hello_message = """To: somebody@example.com
        From: root@localhost
        Subject: Hello World!

        Sent via aiosmtplib
    """

    async def send_with_proxy_header(message):
        header = aiosmtplib.proxy_protocol_header(
            source=(IPv4Address("192.0.2.1"), 51234),
            destination=(IPv4Address("203.0.113.5"), 25),
        )
        await aiosmtplib.send(
            message,
            sender="root@localhost",
            recipients=["somebody@example.com"],
            hostname="203.0.113.5",
            port=25,
            proxy_protocol_header=header,
        )

    asyncio.run(send_with_proxy_header(hello_message))

Omitting ``source`` and ``destination`` sends the v2 LOCAL (or v1 UNKNOWN)
form, for connections made on the proxy's own behalf, such as health checks.

.. _HAProxy PROXY protocol: https://www.haproxy.org/download/1.8/doc/proxy-protocol.txt

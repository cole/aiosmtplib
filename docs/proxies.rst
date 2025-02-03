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

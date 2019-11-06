.. module:: aiosmtplib
    :noindex:

User's Guide
============

Sending Messages
----------------

Sending Message Objects
~~~~~~~~~~~~~~~~~~~~~~~

To send a message, create an :py:class:`email.message.EmailMessage` object, set
appropriate headers ("From" and one of "To", "Cc" or "Bcc", at minimum), then
pass it to :func:`send` with the hostname and port of an SMTP server.

For details on creating :py:class:`email.message.EmailMessage` objects, see
`the stdlib documentation examples
<https://docs.python.org/3.7/library/email.examples.html>`_.

.. note:: Confusingly, :py:class:`email.message.Message` objects are part of the
    legacy email API (prior to Python 3.3), while :py:class:`email.message.EmailMessage`
    objects support email policies other than the older :py:class:`email.policy.Compat32`.

    Use :py:class:`email.message.EmailMessage` where possible; it makes headers easier to
    work with.

.. testcode::

    import asyncio
    from email.message import EmailMessage

    import aiosmtplib

    async def send_hello_world():
        message = EmailMessage()
        message["From"] = "root@localhost"
        message["To"] = "somebody@example.com"
        message["Subject"] = "Hello World!"
        message.set_content("Sent via aiosmtplib")

        await aiosmtplib.send(message, hostname="127.0.0.1", port=1025)

    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(send_hello_world())


Multipart Messages
~~~~~~~~~~~~~~~~~~

Pass :py:class:`email.mime.multipart.MIMEMultipart` objects to :func:`send` to
send messages with both HTML text and plain text alternatives.

.. testcode::

    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText


    message = MIMEMultipart("alternative")
    message["From"] = "root@localhost"
    message["To"] = "somebody@example.com"
    message["Subject"] = "Hello World!"

    plain_text_message = MIMEText("Sent via aiosmtplib", "plain", "utf-8")
    html_message = MIMEText(
        "<html><body><h1>Sent via aiosmtplib</h1></body></html>", "html", "utf-8"
    )
    message.attach(plain_text_message)
    message.attach(html_message)


Sending Raw Messages
~~~~~~~~~~~~~~~~~~~~

You can also send a ``str`` or ``bytes`` message, by providing the ``sender``
and ``recipients`` keyword arguments.

.. testcode::

    import asyncio

    import aiosmtplib

    async def send_hello_world():
        message = """To: somebody@example.com
        From: root@localhost
        Subject: Hello World!

        Sent via aiosmtplib
        """

        await aiosmtplib.send(
            message,
            sender="root@localhost",
            recipients=["somebody@example.com"],
            hostname="127.0.0.1",
            port=1025
        )

    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(send_hello_world())


Authentication
--------------

To authenticate, pass the ``username`` and ``password`` keyword arguments to
:func:`send`.

.. code-block:: python

    await send(
        message,
        hostname="127.0.0.1",
        port=1025,
        username="test",
        password="test"
    )


Connection Options
------------------

Connecting Over TLS/SSL
~~~~~~~~~~~~~~~~~~~~~~~

If an SMTP server supports direct connection via TLS/SSL, pass
``use_tls=True``.

.. code-block:: python

    await send(message, hostname="smtp.gmail.com", port=465, use_tls=True)


STARTTLS connections
~~~~~~~~~~~~~~~~~~~~

Many SMTP servers support the STARTTLS extension over port 587. When using
STARTTLS, the initial connection is made over plaintext, and after connecting
a STARTTLS command is sent, which initiates the upgrade to a secure connection.
To connect to a server that uses STARTTLS, set ``start_tls`` to ``True``.

.. code-block:: python

    await send(message, hostname="smtp.gmail.com", port=587, start_tls=True)

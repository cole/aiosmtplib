.. module:: aiosmtplib
    :noindex:

The SMTP Client Class
=====================

Use the :class:`SMTP` class as a client directly when you want more control
over the email sending process than the :func:`send` async function provides.


Connecting to an SMTP Server
----------------------------

Initialize a new :class:`SMTP` instance, then await its :meth:`SMTP.connect`
coroutine. Initializing an instance does not automatically connect to the
server, as that is a blocking operation.

.. testcode::

    import asyncio

    from aiosmtplib import SMTP


    client = SMTP()
    asyncio.run(client.connect(hostname="127.0.0.1", port=1025))


Connecting over TLS/SSL
~~~~~~~~~~~~~~~~~~~~~~~

For details on different connection types, see :ref:`connection-types`.

If an SMTP server supports direct connection via TLS/SSL, pass ``use_tls=True``
when initializing the SMTP instance (or when calling :meth:`SMTP.connect`).

.. code-block:: python

    smtp_client = aiosmtplib.SMTP(hostname="smtp.gmail.com", port=465, use_tls=True)
    await smtp_client.connect()


STARTTLS connections
~~~~~~~~~~~~~~~~~~~~

For details on different connection types, see :ref:`connection-types`.

By default, if the server advertises STARTTLS support, aiosmtplib will
upgrade the connection automatically. Setting ``use_tls=True`` for STARTTLS
servers will typically result in a connection error.

To opt out of STARTTLS on connect, pass ``start_tls=False``. You may then
manually call :meth:`SMTP.starttls` if needed.

.. code-block:: python

    smtp_client = aiosmtplib.SMTP(
        hostname="smtp.gmail.com",
        port=587,
        start_tls=False,
        use_tls=False,
    )
    await smtp_client.connect()
    await smtp_client.starttls()


Connecting via async context manager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Instances of the :class:`SMTP` class can also be used as an async context
manager, which will automatically connect/disconnect on entry/exit.

.. testcode::

    import asyncio
    from email.message import EmailMessage

    from aiosmtplib import SMTP


    async def say_hello():
        message = EmailMessage()
        message["From"] = "root@localhost"
        message["To"] = "somebody@example.com"
        message["Subject"] = "Hello World!"
        message.set_content("Sent via aiosmtplib")

        smtp_client = SMTP(hostname="127.0.0.1", port=1025)
        async with smtp_client:
            await smtp_client.send_message(message)

    asyncio.run(say_hello())



Sending Messages
----------------

:meth:`SMTP.send_message`
~~~~~~~~~~~~~~~~~~~~~~~~~

Use this method to send :py:class:`email.message.EmailMessage` objects, including
:py:mod:`email.mime` subclasses such as :py:class:`email.mime.text.MIMEText`.

For details on creating :py:class:`email.message.EmailMessage` objects, see `the
stdlib documentation examples
<https://docs.python.org/3.11/library/email.examples.html>`_.

.. testcode::

    import asyncio
    from email.mime.text import MIMEText

    from aiosmtplib import SMTP


    mime_message = MIMEText("Sent via aiosmtplib")
    mime_message["From"] = "root@localhost"
    mime_message["To"] = "somebody@example.com"
    mime_message["Subject"] = "Hello World!"

    async def send_with_send_message(message):
        smtp_client = SMTP(hostname="127.0.0.1", port=1025)
        await smtp_client.connect()
        await smtp_client.send_message(message)
        await smtp_client.quit()

    asyncio.run(send_with_send_message(mime_message))


Pass :py:class:`email.mime.multipart.MIMEMultipart` objects to
:meth:`SMTP.send_message` to send messages with both HTML text and plain text
alternatives.

.. testcode::

    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    message = MIMEMultipart("alternative")
    message["From"] = "root@localhost"
    message["To"] = "somebody@example.com"
    message["Subject"] = "Hello World!"

    message.attach(MIMEText("hello", "plain", "utf-8"))
    message.attach(MIMEText("<html><body><h1>Hello</h1></body></html>", "html", "utf-8"))

    async def send_multipart_message(message):
        smtp_client = SMTP(hostname="127.0.0.1", port=1025)
        await smtp_client.connect()
        await smtp_client.send_message(message)
        await smtp_client.quit()

    asyncio.run(send_multipart_message(message))


:meth:`SMTP.sendmail`
~~~~~~~~~~~~~~~~~~~~~

Use :meth:`SMTP.sendmail` to send raw messages. Note that when using this
method, you must format the message headers yourself.

.. testcode::

    import asyncio

    from aiosmtplib import SMTP


    sender = "root@localhost"
    recipients = ["somebody@example.com"]
    message = """To: somebody@example.com
    From: root@localhost
    Subject: Hello World!

    Sent via aiosmtplib
    """

    async def send_with_sendmail():
        smtp_client = SMTP(hostname="127.0.0.1", port=1025)
        await smtp_client.connect()
        await smtp_client.sendmail(sender, recipients, message)
        await smtp_client.quit()

    asyncio.run(send_with_sendmail())


Timeouts
--------

All commands accept a ``timeout`` keyword argument of a numerical value in
seconds. This value is used for all socket operations, and will raise
:exc:`.SMTPTimeoutError` if exceeded. Timeout values passed to :func:`send` and
:meth:`SMTP.__init__` will be used as the default value for commands executed
on the connection.

The default timeout is 60 seconds.


Parallel Execution
------------------

SMTP is a sequential protocol. Multiple commands must be sent to send an email,
and they must be sent in the correct sequence. As a consequence of this,
executing multiple :meth:`SMTP.send_message` tasks in parallel (i.e. with
:py:func:`asyncio.gather`) is not any more efficient than executing in
sequence, as the client must wait until one mail is sent before beginning the
next.

If you have a lot of emails to send, consider creating multiple connections
(:class:`SMTP` instances) and splitting the work between them.

.. module:: aiosmtplib

Overview
========

aiosmtplib is an asynchronous SMTP client for use with asyncio.


Quickstart
----------

.. testcode::

    import asyncio
    from email.mime.text import MIMEText

    import aiosmtplib

    loop = asyncio.get_event_loop()
    smtp = aiosmtplib.SMTP(hostname="127.0.0.1", port=1025, loop=loop)
    loop.run_until_complete(smtp.connect())

    message = MIMEText("Sent via aiosmtplib")
    message["From"] = "root@localhost"
    message["To"] = "somebody@example.com"
    message["Subject"] = "Hello World!"

    loop.run_until_complete(smtp.send_message(message))


Requirements
------------
Python 3.5.2+, compiled with SSL support, is required.


Connecting to an SMTP Server
----------------------------

Initialize a new :class:`SMTP` instance, then await its :meth:`SMTP.connect`
coroutine. Initializing an instance does not automatically connect to the
server, as that is a blocking operation.

.. Since this code requires a server on port 25, don't test it, at least for
   now.

.. code-block:: python

    client = SMTP()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(client.connect(hostname="localhost", port=25))



Connecting over TLS/SSL
~~~~~~~~~~~~~~~~~~~~~~~

If an SMTP server supports direct connection via TLS/SSL, pass ``use_tls=True``
when initializing the SMTP instance (or when calling :meth:`SMTP.connect`).

.. Since this code requires Gmail, don't test it, at least for now.

.. code-block:: python


    loop = asyncio.get_event_loop()
    smtp = aiosmtplib.SMTP(hostname="smtp.gmail.com", port=465, loop=loop, use_tls=True)
    loop.run_until_complete(smtp.connect())


STARTTLS connections
~~~~~~~~~~~~~~~~~~~~
Many SMTP servers support the STARTTLS extension over port 587. When using
STARTTLS, the initial connection is made over plaintext, and after connecting
a STARTTLS command is sent which initiates the upgrade to a secure connection.
To connect to a server that uses STARTTLS, set ``use_tls`` to ``False`` when
connecting, and call :meth:`SMTP.starttls` on the client.

.. Since this code requires Gmail, don't test it, at least for now.

.. code-block:: python

    loop = asyncio.get_event_loop()
    smtp = aiosmtplib.SMTP(hostname="smtp.gmail.com", port=587, loop=loop, use_tls=False)
    loop.run_until_complete(smtp.connect())
    loop.run_until_complete(smtp.starttls())


Connecting via async context manager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Instances of the :class:`SMTP` class can also be used as an async context
manager, which will automatically connect/disconnect on entry/exit.

.. testcode::

    async def send_message():
        message = MIMEText("Sent via aiosmtplib")
        message["From"] = "root@localhost"
        message["To"] = "somebody@example.com"
        message["Subject"] = "Hello World!"

        async with aiosmtplib.SMTP(hostname="127.0.0.1", port=1025, loop=loop):
            smtp.send_message(message)

    loop.run_until_complete(send_message())


Sending Messages
----------------

:meth:`SMTP.send_message`
~~~~~~~~~~~~~~~~~~~~~~~~~

This is the simplest API, and is the recommended way to send messages, as it
makes it easy to set headers correctly and handle multi part messages. For
details on creating :class:`email.message.Message` objects, see `the
stdlib documentation examples
<https://docs.python.org/3.6/library/email.examples.html>`_.

Use :meth:`SMTP.send_message` to send :class:`email.message.Message` objects,
including :mod:`email.mime` subclasses such as
:class:`email.mime.text.MIMEText`.

.. testcode::

    from email.mime.text import MIMEText

    message = MIMEText("Sent via aiosmtplib")
    message["From"] = "root@localhost"
    message["To"] = "somebody@example.com"
    message["Subject"] = "Hello World!"

    loop = asyncio.get_event_loop()
    loop.run_until_complete(smtp.send_message(message))


Pass :class:`email.mime.multipart.MIMEMultipart` objects to
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

    loop = asyncio.get_event_loop()
    loop.run_until_complete(smtp.send_message(message))



:meth:`SMTP.sendmail`
~~~~~~~~~~~~~~~~~~~~~

Use :meth:`SMTP.sendmail` to send raw messages. Note that when using this
method, you must format the message headers yourself.

.. testcode::

    sender = "root@localhost"
    recipients = ["somebody@example.com"]
    message = """To: somebody@example.com
    From: root@localhost
    Subject: Hello World!

    Sent via aiosmtplib
    """

    loop = asyncio.get_event_loop()
    loop.run_until_complete(smtp.sendmail(sender, recipients, message))


Timeouts
--------
All commands accept a ``timeout`` keyword argument of a numerical value in
seconds. This value is used for all socket operations, and will raise
:exc:`.SMTPTimeoutError` if exceeded. Timeout values passed to
:meth:`SMTP.__init__` or :meth:`SMTP.connect` will be used as the default value
for commands executed on the connection.

The default timeout is 60 seconds.


Parallel Execution
------------------
SMTP is a sequential protocol. Multiple commands must be sent to send an
email, and they must be sent in the correct sequence. As a consequence of
this, executing multiple :meth:`SMTP.sendmail` tasks in parallel (i.e. with
:func:`asyncio.gather`) is not any more efficient than executing in sequence,
as the client must wait until one mail is sent before beginning the next.

If you have a lot of emails to send, consider creating multiple connections
(:class:`SMTP` instances) and splitting the work between them.


Bug reporting
-------------
Bug reports (and feature requests) are welcome via Github issues.

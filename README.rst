aiosmtplib
==========

|travis| |pypi-version| |pypi-python-versions| |pypi-status| |pypi-license|

------------


Introduction
------------

aiosmtplib is an SMTP client for use with asyncio.

Basic usage:

.. code-block:: python

    import asyncio
    import aiosmtplib

    loop = asyncio.get_event_loop()
    smtp = aiosmtplib.SMTP(hostname='localhost', port=1025, loop=loop)
    loop.run_until_complete(smtp.connect())

    async def send_a_message():
        sender = 'root@localhost'
        recipient = 'somebody@localhost'
        message = "Hello World"
        await smtp.sendmail(sender, [recipient], message)

    loop.run_until_complete(send_a_message())


Requirements
------------
Python 3.5.3+, compiled with SSL support, is required.

Connecting to an SMTP server
----------------------------

Initialize a new ``aiosmtplib.SMTP`` instance, then run its ``connect``
coroutine. Unlike in smtplib, initializing an instance does not automatically
connect to the server, as that is a blocking operation.

Allowed arguments to initialize the client (or the ``connect`` method):

``hostname``
    Server name (or IP) to connect to
``port``
    Server port as an integer. Defaults to 25 if ``use_tls`` is False, 465
    if ``use_tls`` is True.
``source_address``
    The hostname of the client. Defaults to the result of
    ``socket.getfqdn()``. Note that this call blocks.
``timeout``
    Default timeout value for all operations, in seconds. Defaults to 60.
``loop``
    IOLoop instance to run on. Defaults to ``asyncio.get_event_loop()``.
``use_tls``
    If True, make the initial connection to the server over TLS/SSL. Note
    that if the server supports STARTTLS only, this should be False; see
    `STARTTLS`_ below.
``validate_certs``
    Determines if server certificates are validated if using ``use_tls``.
    Defaults to True.
``client_cert``
    Path to client side certificate, if one is to be used for the TLS
    connection.
``client_cert``
    Path to client side key, if one is to be used for the TLS connection.
``tls_context``
    An SSLContext object, used for the TLS connection. Mutually exclusive
    with ``client_cert``/``client_key``.


Sending messages
----------------

Use ``SMTP.sendmail`` to send raw messages. Allowed arguments are:

``sender``
    The address sending this mail.
``recipients``
    A list of addresses to send this mail to.  A bare string will be treated
    as a list with 1 address.
``message``
    The message string to send.
``mail_options``
    List of options (such as ESMTP 8bitmime) for the mail command.
``rcpt_options``
    List of options (such as DSN commands) for all the rcpt commands.

Use ``SMTP.send_message`` to send ``email.message.Message`` objects.

Timeouts
--------
All commands accept a ``timeout`` keyword argument of a numerical value in
seconds. This value is used for all socket operations, and will raise
``STMPTimeoutError`` if exceeded. Timeout values passed to init or ``connect``
will be used as the default value for commands executed on the connection.

The default timeout is 60 seconds.


STARTTLS
--------
Many SMTP servers support the STARTTLS extension over port 587. To connect to
one of these, set ``use_tls`` to False, and call ``starttls`` on the client.

.. code-block:: python

    loop = asyncio.get_event_loop()
    smtp = aiosmtplib.SMTP(
        hostname='smtp.gmail.com', port=587, loop=loop, use_tls=False)
    loop.run_until_complete(smtp.connect())
    loop.run_until_complete(smtp.starttls())


Parallel execution
------------------
SMTP is a sequential protocol. Multiple commands must be sent to send an
email, and they must be sent in the correct sequence. As a consequence of
this, executing multiple sendmail tasks in parallell (i.e. with 
``asyncio.gather``) is not any more efficient than executing in sequence, as
the client must wait until one mail is sent before beginning the next.

If you have a lot of emails to send, consider creating multiple connections
(``SMTP`` instances) and splitting the work between them.


Roadmap
-------
aiosmtplib is now feature complete, however test coverage and documentation
need a lot of work. Feature requests and bug reports are welcome via Github
issues.


.. |travis| image:: https://travis-ci.org/cole/aiosmtplib.svg?branch=master
           :target: https://travis-ci.org/cole/aiosmtplib
           :alt: "aiosmtplib TravisCI build status"
.. |pypi-version| image:: https://img.shields.io/pypi/v/aiosmtplib.svg
           :target: https://pypi.python.org/pypi/aiosmtplib
           :alt: "aiosmtplib on the Python Package Index"
.. |pypi-python-versions| image:: https://img.shields.io/pypi/pyversions/aiosmtplib.svg
.. |pypi-status| image:: https://img.shields.io/pypi/status/aiosmtplib.svg
.. |pypi-license| image:: https://img.shields.io/pypi/l/aiosmtplib.svg

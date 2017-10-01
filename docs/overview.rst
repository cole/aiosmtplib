.. module:: aiosmtplib

.. testsetup:: *
    
    import asyncio

    from aiosmtpd.controller import Controller

    import aiosmtplib
    from aiosmtplib import SMTP

    controller = Controller(object(), hostname='localhost', port=10025)
    controller.start()

.. testcleanup:: *

    controller.stop()

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
    smtp = aiosmtplib.SMTP(hostname='localhost', port=10025, loop=loop)
    loop.run_until_complete(smtp.connect())

    message = MIMEText('Sent via aiosmtplib')
    message['From'] = 'root@localhost'
    message['To'] = 'somebody@example.com'
    message['Subject'] = 'Hello World!'

    loop.run_until_complete(smtp.send_message(message))


Requirements
------------
Python 3.5+, compiled with SSL support, is required.


Connecting to an SMTP server
----------------------------

Initialize a new :class:`SMTP` instance, then await its
:meth:`SMTP.connect` coroutine. Initializing an instance does not
automatically connect to the server, as that is a blocking operation.

.. testcode::

    gmail_client = SMTP()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        gmail_client.connect(hostname='smtp.gmail.com', port=587))


Sending messages
----------------

:meth:`SMTP.send_message`
~~~~~~~~~~~~~~~~~~~~~~~~~

Use :meth:`SMTP.send_message` to send :class:`email.message.Message` objects.

.. testcode::

    message = MIMEText('Sent via aiosmtplib')
    message['From'] = 'root@localhost'
    message['To'] = 'somebody@example.com'
    message['Subject'] = 'Hello World!'

    loop = asyncio.get_event_loop()
    loop.run_until_complete(smtp.send_message(message))


This is the simplest API, and is the recommended way to send messages, as it
makes it easy to set headers correctly and handle multi part messages. For
details on creating :class:`email.message.Message` objects, see `the
stdlib documentation examples
<https://docs.python.org/3.5/library/email-examples.html>`_.


:meth:`SMTP.sendmail`
~~~~~~~~~~~~~~~~~~~~~

Use :meth:`SMTP.sendmail` to send raw messages.

.. testcode::

    sender = 'root@localhost'
    recipients = ['somebody@example.com']
    message = '''To: somebody@example.com
    From: root@localhost
    Subject: Hello World!

    Sent via aiosmtplib
    '''

    loop = asyncio.get_event_loop()
    loop.run_until_complete(smtp.sendmail(sender, recipients, message))


Note that when using this method, you must format the message headers yourself.


STARTTLS Connections
--------------------
Many SMTP servers support the STARTTLS extension over port 587. To connect to
one of these, set ``use_tls`` to ``False`` when connecting, and call
:meth:`SMTP.starttls` on the client.


.. testcode::

    loop = asyncio.get_event_loop()
    smtp = aiosmtplib.SMTP(
        hostname='smtp.gmail.com', port=587, loop=loop, use_tls=False)
    loop.run_until_complete(smtp.connect())
    loop.run_until_complete(smtp.starttls())


Timeouts
--------
All commands accept a ``timeout`` keyword argument of a numerical value in
seconds. This value is used for all socket operations, and will raise
:exc:`.SMTPTimeoutError` if exceeded. Timeout values passed to
:meth:`SMTP.__init__` or :meth:`SMTP.connect` will be used as the default value
for commands executed on the connection.

The default timeout is 60 seconds.


Parallel execution
------------------
SMTP is a sequential protocol. Multiple commands must be sent to send an
email, and they must be sent in the correct sequence. As a consequence of
this, executing multiple :meth:`SMTP.sendmail` tasks in parallel (i.e. with 
:func:`asyncio.gather`) is not any more efficient than executing in sequence,
as the client must wait until one mail is sent before beginning the next.

If you have a lot of emails to send, consider creating multiple connections
(:class:`SMTP` instances) and splitting the work between them.


Roadmap
-------
:mod:`aiosmtplib` is now feature complete, however test coverage and
documentation need a lot of work. Feature requests and bug reports are welcome
via Github issues.




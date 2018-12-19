aiosmtplib
==========

|travis| |codecov| |pypi-version| |pypi-python-versions| |pypi-status|
|pypi-license| |black|

------------

aiosmtplib is an asynchronous SMTP client for use with asyncio.

For complete documentation, see `Read The Docs`_.


Quickstart
----------

.. code-block:: python

    import asyncio
    from email.mime.text import MIMEText

    import aiosmtplib

    loop = asyncio.get_event_loop()
    smtp = aiosmtplib.SMTP(hostname='127.0.0.1', port=1025, loop=loop)
    loop.run_until_complete(smtp.connect())

    message = MIMEText('Sent via aiosmtplib')
    message['From'] = 'root@localhost'
    message['To'] = 'somebody@example.com'
    message['Subject'] = 'Hello World!'

    loop.run_until_complete(smtp.send_message(message))


Requirements
------------
Python 3.5.2+, compiled with SSL support, is required.


Connecting to an SMTP server
----------------------------

Initialize a new ``SMTP`` instance, then await its
``connect`` coroutine. Initializing an instance does not
automatically connect to the server, as that is a blocking operation.

.. code-block:: python

    gmail_client = SMTP()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        gmail_client.connect(hostname='smtp.gmail.com', port=587))


Sending messages
----------------

``SMTP.send_message``
~~~~~~~~~~~~~~~~~~~~~

Use ``send_message`` to send ``email.message.Message`` objects.

.. code-block:: python

    message = MIMEText('Sent via aiosmtplib')
    message['From'] = 'root@localhost'
    message['To'] = 'somebody@example.com'
    message['Subject'] = 'Hello World!'

    loop = asyncio.get_event_loop()
    loop.run_until_complete(smtp.send_message(message))


This is the simplest API, and is the recommended way to send messages, as it
makes it easy to set headers correctly and handle multi part messages. For
details on creating ``email.message.Message`` objects, see `the
stdlib documentation examples
<https://docs.python.org/3.5/library/email-examples.html>`_.


``SMTP.sendmail``
~~~~~~~~~~~~~~~~~

Use ``sendmail`` to send raw messages.

.. code-block:: python

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
``starttls`` on the client.


.. code-block:: python

    loop = asyncio.get_event_loop()
    smtp = aiosmtplib.SMTP(
        hostname='smtp.gmail.com', port=587, loop=loop, use_tls=False)
    loop.run_until_complete(smtp.connect())
    loop.run_until_complete(smtp.starttls())


Roadmap
-------
aiosmtplib is now feature complete, however test coverage and documentation
need a lot of work. Feature requests and bug reports are welcome
via Github issues.



.. |travis| image:: https://travis-ci.org/cole/aiosmtplib.svg?branch=master
           :target: https://travis-ci.org/cole/aiosmtplib
           :alt: "aiosmtplib TravisCI build status"
.. |pypi-version| image:: https://img.shields.io/pypi/v/aiosmtplib.svg
                 :target: https://pypi.python.org/pypi/aiosmtplib
                 :alt: "aiosmtplib on the Python Package Index"
.. |pypi-python-versions| image:: https://img.shields.io/pypi/pyversions/aiosmtplib.svg
.. |pypi-status| image:: https://img.shields.io/pypi/status/aiosmtplib.svg
.. |pypi-license| image:: https://img.shields.io/pypi/l/aiosmtplib.svg
.. |codecov| image:: https://codecov.io/gh/cole/aiosmtplib/branch/master/graph/badge.svg
             :target: https://codecov.io/gh/cole/aiosmtplib
.. |black| image:: https://img.shields.io/badge/code%20style-black-000000.svg
           :target: https://github.com/ambv/black
           :alt: "Code style: black"
.. _Read The Docs: https://aiosmtplib.readthedocs.io/en/latest/

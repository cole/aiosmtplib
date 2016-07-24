aiosmtplib
==========

Introduction
------------

Aiosmtplib is an implementation of the python stdlib smtplib using asyncio, for
use in asynchronous applications.

Basic usage::

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



Connecting to an SMTP server
----------------------------

Initialize a new ``aiosmtplib.SMTP`` instance, then run it's ``connect``
coroutine. Unlike the standard smtplib, initializing an instance does not
automatically connect to the server.

Sending messages
----------------

Use ``SMTP.sendmail`` to send raw messages. Allowed arguments are:
    - sender       : The address sending this mail.
    - recipients   : A list of addresses to send this mail to.  A bare
                     string will be treated as a list with 1 address.
    - message      : The message string to send.
    - mail_options : List of options (such as ESMTP 8bitmime) for the
                     mail command.
    - rcpt_options : List of options (such as DSN commands) for
                     all the rcpt commands.

Use ``SMTP.send_message`` to send ``email.message.Message`` objects.

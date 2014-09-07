# aiosmtplib

## Introduction

Aiosmtplib is an implementation of the python stdlib smtplib using asyncio, for
use in asynchronous applications.

Basic usage:

    import asyncio
    import aiosmtplib
    loop = asyncio.get_event_loop()
    smtp = aiosmtplib.SMTP(hostname='localhost', port=25, loop=loop)
    
    @asyncio.coroutine
    def send_a_message():
        sender = 'root@localhost'
        recipient = 'somebody@localhost'
        message = "Hello World"
        yield from smtp.sendmail(sender, recipients, message)
    
    asyncio.async(send_a_message())
    loop.run_forever()


## Connecting to an SMTP server

Use an instance of the `SMTP` class to connect to a server. Note that if the
event loop used to initialize the class is not currently running, it will be
started in order to connect.

## Sending messages

Use `SMTP.sendmail` to send raw messages. The method signature is the same as
for standard smtplib.

Use `SMTP.send_message` to send `email.message.Message` objects. The method
signature is the same as for standard smtplib.
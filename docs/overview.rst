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


.. include:: ../README.rst
    :start-line: 13

.. testsetup:: *
    
    import asyncio

    from aiosmtpd.controller import Controller

    import aiosmtplib
    from aiosmtplib import SMTP, SMTPResponse

    controller = Controller(object(), hostname='localhost', port=10025)
    controller.start()

.. testcleanup:: *

    controller.stop()


Overview
========

.. include:: ../README.rst
    :start-line: 8

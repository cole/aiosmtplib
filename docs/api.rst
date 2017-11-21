.. testsetup:: *
    
    import asyncio
    import logging

    from aiosmtpd.controller import Controller

    import aiosmtplib
    from aiosmtplib import SMTP, SMTPResponse

    aiosmtpd_logger = logging.getLogger('mail.log')
    aiosmtpd_logger.setLevel(logging.ERROR)

    controller = Controller(object(), hostname='localhost', port=0)
    controller.start()
    port = controller.server.sockets[0].getsockname()[1]

    smtp = SMTP(hostname='localhost', port=port)

.. testcleanup:: *

    controller.stop()


API Reference
==============

The SMTP class
--------------

.. autoclass:: aiosmtplib.SMTP
    :members:
    :inherited-members:

    .. automethod:: aiosmtplib.SMTP.__init__


Server Responses
----------------

.. autoclass:: aiosmtplib.response.SMTPResponse
    :members:


Status Codes
------------

.. autoclass:: aiosmtplib.status.SMTPStatus
    :members:
    :undoc-members:


Exceptions
----------

.. automodule:: aiosmtplib.errors
    :members:
    :show-inheritance:


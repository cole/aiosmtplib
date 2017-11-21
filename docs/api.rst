.. testsetup:: *
    
    import asyncio
    import logging

    from aiosmtpd.controller import Controller

    import aiosmtplib
    from aiosmtplib import SMTP, SMTPResponse

    aiosmtpd_logger = logging.getLogger('mail.log')
    aiosmtpd_logger.setLevel(logging.ERROR)

    controller = Controller(object(), hostname='0.0.0.0', port=0)
    controller.start()
    hostname, port = controller.server.sockets[0].getsockname()

    smtp = SMTP(hostname=hostname, port=port)

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


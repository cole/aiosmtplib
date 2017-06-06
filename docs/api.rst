.. testsetup:: *
    
    import asyncio

    from aiosmtpd.controller import Controller

    import aiosmtplib
    from aiosmtplib import SMTP, SMTPResponse

    controller = Controller(object(), hostname='localhost', port=10025)
    controller.start()

    smtp = SMTP(hostname='localhost', port=10025)

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


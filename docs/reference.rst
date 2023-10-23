API Reference
=============

.. testsetup::

    import aiosmtplib
    from aiosmtplib import SMTPResponse


The send Coroutine
------------------

Use the :func:`aiosmtplib.send` coroutine in most cases when you want to send a message.

.. autofunction:: aiosmtplib.send


The SMTP Class
--------------

The lower level :class:`aiosmtplib.SMTP` class gives you more control over the SMTP connection.

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

.. autoclass:: aiosmtplib.typing.SMTPStatus
    :members:
    :undoc-members:


Exceptions
----------

.. automodule:: aiosmtplib.errors
    :members:
    :show-inheritance:

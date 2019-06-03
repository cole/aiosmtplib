API Reference
=============

.. testsetup::

    import aiosmtplib
    from aiosmtplib import SMTPResponse


The send message API
--------------------

.. autofunction:: aiosmtplib.send_message


The SMTP Class
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

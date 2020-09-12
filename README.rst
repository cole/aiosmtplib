aiosmtplib
==========

|circleci| |codecov| |pypi-version| |pypi-python-versions| |pypi-status|
|pypi-license| |black|

------------

aiosmtplib is an asynchronous SMTP client for use with asyncio.

For documentation, see `Read The Docs`_.

Quickstart
----------

.. code-block:: python

    import asyncio
    from email.message import EmailMessage

    import aiosmtplib

    message = EmailMessage()
    message["From"] = "root@localhost"
    message["To"] = "somebody@example.com"
    message["Subject"] = "Hello World!"
    message.set_content("Sent via aiosmtplib")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(aiosmtplib.send(message, hostname="127.0.0.1", port=25))


Requirements
------------
Python 3.6+, compiled with SSL support, is required.


Bug reporting
-------------
Bug reports (and feature requests) are welcome via Github issues.



.. |circleci| image:: https://circleci.com/gh/cole/aiosmtplib/tree/master.svg?style=shield
           :target: https://circleci.com/gh/cole/aiosmtplib/tree/master
           :alt: "aiosmtplib CircleCI build status"
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
.. _Read The Docs: https://aiosmtplib.readthedocs.io/en/stable/overview.html

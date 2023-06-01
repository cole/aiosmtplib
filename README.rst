aiosmtplib
==========

|circleci| |precommit.ci| |codecov| |pypi-version| |pypi-status| |downloads| |pypi-python-versions|
|pypi-license|

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

    asyncio.run(aiosmtplib.send(message, hostname="127.0.0.1", port=25))


Requirements
------------
Python 3.8+, compiled with SSL support, is required.


Bug Reporting
-------------
Bug reports (and feature requests) are welcome via `Github issues`_.



.. |circleci| image:: https://circleci.com/gh/cole/aiosmtplib/tree/main.svg?style=shield
           :target: https://circleci.com/gh/cole/aiosmtplib/tree/main
           :alt: "aiosmtplib CircleCI build status"
.. |pypi-version| image:: https://img.shields.io/pypi/v/aiosmtplib.svg
                 :target: https://pypi.python.org/pypi/aiosmtplib
                 :alt: "aiosmtplib on the Python Package Index"
.. |pypi-python-versions| image:: https://img.shields.io/pypi/pyversions/aiosmtplib.svg
.. |pypi-status| image:: https://img.shields.io/pypi/status/aiosmtplib.svg
.. |pypi-license| image:: https://img.shields.io/pypi/l/aiosmtplib.svg
.. |codecov| image:: https://codecov.io/gh/cole/aiosmtplib/branch/main/graph/badge.svg
             :target: https://codecov.io/gh/cole/aiosmtplib
.. |downloads| image:: https://pepy.tech/badge/aiosmtplib
               :target: https://pepy.tech/project/aiosmtplib
               :alt: "aiosmtplib on pypy.tech"
.. |precommit.ci| image:: https://results.pre-commit.ci/badge/github/cole/aiosmtplib/main.svg
                  :target: https://results.pre-commit.ci/latest/github/cole/aiosmtplib/main
                  :alt: "pre-commit.ci status"
.. _Read The Docs: https://aiosmtplib.readthedocs.io/en/stable/overview.html
.. _Github issues: https://github.com/cole/aiosmtplib/issues

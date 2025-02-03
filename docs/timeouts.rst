 .. py:currentmodule:: aiosmtplib

Timeouts
========

The :func:`send` coroutine and most :class:`SMTP` operations (
:meth:`SMTP.__init__`, :meth:`SMTP.connect`, and most command operations, e.g.
:meth:`SMTP.ehlo`) accept a ``timeout`` keyword argument of a numerical value
in seconds. This value is used for all socket operations (initial connection,
STARTTLS, each command/response, etc), and will raise :exc:`.SMTPTimeoutError`
if exceeded.

.. warning:: Note that because the timeout is on socket operations, as long as
    there is no period of inactivity that exceeds it (meaning no individual bytes
    sent or received), the timeout will not be triggered. This means that if you
    set the timeout to 1 second (for example), sending an entire message might
    take much longer than that *without* a timeout occurring.

Timeout values passed directly to :class:`SMTP` command methods will override
the default passed in on initialization.

The default timeout is 60 seconds.

.. module:: aiosmtplib
    :noindex:

Timeouts
========

The :func:`send` coroutine and :meth:`SMTP.__init__`  accept a ``timeout``
keyword argument of a numerical value in seconds. This value is used for all
socket operations (initial connection, STARTTLS, each command/response, etc),
and will raise :exc:`.SMTPTimeoutError` if exceeded.

Timeout values passed directly to :class:`SMTP` command methods will override
the default passed in on initialization.

The default timeout is 60 seconds.

Changelog
=========

3.0.0 (unreleased)
------------------

- **BREAKING**: Drop Python 3.7 support.
- **BREAKING**: Positional and keyword argument usage is now enforced.
- Change: don't use timeout value passed to ``connect`` everywhere,
  only for the initial connection (credit @wombatonfire)


2.0.2
-----

- Bugfix: don't send extra EHLO/HELO before QUIT (credit @ikrivosheev)
- Change: added SMTPConnectionResponseError for invalid response on
  connect only (credit @ikrivosheev)

2.0.1
-----

- Bugfix: "tests" and "docs" in the sdist should be includes, not packages,
  so that they do not get put in ``site-packages``.


2.0.0
-----

- **BREAKING**: Drop Python 3.5 and 3.6 support.
- **BREAKING**: On connect, if the server supports STARTTLS, automatically try
  to upgrade the connection. STARTTLS after connect can be turned on or off
  explicitly by passing ``start_tls=True`` or ``start_tls=False`` respectively.
- **BREAKING**: Remove deprecated ``loop`` keyword argument for the SMTP class.
- Change: The ``source_address`` argument now takes a (addr, port) tuple that is
  passed as the ``local_addr`` param to ``asyncio.create_connection``, allowing
  for binding to a specific IP. The new ``local_hostname`` argument that takes
  the value to be sent to the server with the EHLO/HELO message. This behaviour
  more closely matches ``smtplib``.

  In order to not break existing usage, passing a string instead of a tuple to
  ``source_address`` will give a DeprecationWarning, and use the value as it if
  had been passed for ``local_hostname``.

  Thanks @rafaelrds and @davidmcnabnz for raising and contributing work on this
  issue.
- Bugfix: the ``mail_options`` and ``rcpt_options`` arguments to the ``send``
  coroutine no longer cause errors
- Cleanup: Refactored ``SMTP`` parent classes to remove complex inheritance
  structure.
- Cleanup: Switched to ``asyncio.run`` for sync client methods.
- Cleanup: Don't use private email.message.Message policy attribute (instead,
  set an appropriate policy based on message class)


1.1.7
-----

- Security: Fix a possible injection vulnerability (a variant of
  https://consensys.net/diligence/vulnerabilities/python-smtplib-multiple-crlf-injection/)

  Note that in order to exploit this vulnerability in aiosmtplib, the attacker would need
  control of the ``hostname`` or ``source_address`` parameters. Thanks Sam Sanoop @ Snyk
  for bringing this to my attention.
- Bugfix: include CHANGLOG in sdist release
- Type hints: fix type hints for async context exit (credit @JelleZijlstra)


1.1.6
-----

- Bugfix: fix authenticated test failures (credit @P-EB)


1.1.5
-----

- Bugfix: avoid raising ``asyncio.CancelledError`` on connection lost
- Bugfix: allow UTF-8 chars in usernames and password strings
- Feature: allow bytes type args for login usernames and passwords


1.1.4
-----

- Bugfix: parsing comma separated addresses in to header (credit @gjcarneiro)
- Feature: add py.typed file (PEP 561, credit @retnikt)


1.1.3
-----

- Feature: add pause and resume writing methods to ``SMTPProcotol``, via
  ``asyncio.streams.FlowControlMixin`` (thanks @ikrivosheev).

- Bugfix: allow an empty sender (credit @ikrivosheev)

- Cleanup: more useful error message when login called without TLS


1.1.2
-----

- Bugfix: removed ``docs`` and ``tests`` from wheel, they should only be
  in the source distribution.


1.1.1
-----

- Bugfix: Fix handling of sending legacy email API (Message) objects.

- Bugfix: Fix SMTPNotSupported error with UTF8 sender/recipient names
  on servers that don't support SMTPUTF8.


1.1.0
-----

- Feature: Added send coroutine api.

- Feature: Added SMTPUTF8 support for UTF8 chars in addresses.

- Feature: Added connected socket and Unix socket path connection options.

- Feature: Wait until the connect coroutine is awaited to get the event loop.
  Passing an explicit event loop via the loop keyword argument is deprecated
  and will be removed in version 2.0.

- Cleanup: Set context for timeout and connection exceptions properly.

- Cleanup: Use built in start_tls method on Python 3.7+.

- Cleanup: Timeout correctly if TLS handshake takes too long on Python 3.7+.

- Cleanup: Updated SMTPProcotol class and removed StreamReader/StreamWriter
  usage to remove deprecation warnings in 3.8.

- Bugfix: EHLO/HELO if required before any command, not just when using
  higher level commands.

- Cleanup: Replaced asserts in functions with more useful errors (e.g.
  RuntimeError).

- Cleanup: More useful error messages for timeouts (thanks ikrivosheev!),
  including two new exception classes, ``SMTPConnectTimeoutError`` and
  ``SMTPReadTimeoutError``


1.0.6
-----

- Bugfix: Set default timeout to 60 seconds as per documentation
  (previously it was unlimited).


1.0.5
-----

- Bugfix: Connection is now closed if an error response is received
  immediately after connecting.


1.0.4
-----

- Bugfix: Badly encoded server response messages are now decoded to utf-8,
  with error chars escaped.

- Cleanup: Removed handling for exceptions not raised by asyncio (in
  SMTPProtocol._readline)


1.0.3
-----

- Bugfix: Removed buggy close connection on __del__

- Bugfix: Fixed old style auth method parsing in ESMTP response.

- Bugfix: Cleanup transport on exception in connect method.

- Cleanup: Simplified SMTPProtocol.connection_made, __main__


1.0.2
-----

- Bugfix: Close connection lock on on SMTPServerDisconnected

- Feature: Added cert_bundle argument to connection init, connect and starttls
  methods

- Bugfix: Disconnected clients would raise SMTPResponseException: (-1 ...)
  instead of SMTPServerDisconnected


1.0.1
-----

- Bugfix: Commands were getting out of order when using the client as a context
  manager within a task

- Bugfix: multiple tasks calling connect would get confused

- Bugfix: EHLO/HELO responses were being saved even after disconnect

- Bugfix: RuntimeError on client cleanup if event loop was closed

- Bugfix: CRAM-MD5 auth was not working

- Bugfix: AttributeError on STARTTLS under uvloop


1.0.0
-----

Initial feature complete release with stable API; future changes will be
documented here.

Changelog
=========

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

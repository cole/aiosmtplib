aiosmtplib changes
==================

1.1.0
-----

- Bugfix: EHLO/HELO if required before any command, not just when using
  higher level commands.

- Cleanup: Replaced asserts in functions with more useful errors (e.g.
  RuntimeError).

- Cleanup: More useful error messages for timeouts (thanks ikrivosheev!),
  including two new exception classes, ``SMTPConnectTimeoutError`` and
  ``SMTPReadTimeoutError``

1.0.5
-----

- Bugfix: Connection is now closed if an error response is recieved
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

- Bugfix: Fixed old style auth method parsing in ESMPT response.

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

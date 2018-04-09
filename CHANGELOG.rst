aiosmtplib changes
==================

master
------

- Bugfix: Removed buggy close connection on __del__

- Bugfix: Fixed old style auth method parsing in ESMPT response.


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

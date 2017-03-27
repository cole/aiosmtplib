aiosmtplib changes
==================

master
------

- Bugfix: Commands were getting out of order when using the client as a context
  manager within a task

- Bugfix: multiple tasks calling connect would get confused

- Bugfix: EHLO/HELO responses were being saved even after disconnect

- Bugfix: RuntimeError on client cleanup if event loop was closed

- Bugfix: CRAM-MD5 auth was not working

1.0.0
-----
Initial feature complete release with stable API; future changes will be
documented here.

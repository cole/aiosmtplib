.. _connection-types:

Connection Types
================

aiosmtplib supports the three main types of encryption used by SMTP servers:

1. Plaintext (default port 25). The connection is entirely unencrypted.
   Most authentication methods will not be supported by servers
   when using an unencrypted connection. Although they are best suited for
   connecting to a server running locally or for testing, for historical
   reasons unencrypted connections are the default if no options are specified.
2. TLS/SSL encrypted (default port 465). In this case the TLS handshake
   occurs when the connection is established, and all traffic is encrypted.
   This type of connection should generally be used where available.
3. STARTTLS (default port 587). When using STARTTLS, an initial unencrypted
   connection is made, EHLO/HELO greetings are exchanged, and the connection
   is upgraded in place once the client requests it by sending the STARTTLS
   command. Most servers require an upgrade before allowing AUTH commands.

.. note:: As of version 2.0, if the server advertises STARTTLS, aiosmtplib
    will automatically initiate STARTTLS on connect. If this behaviour
    causes problems, you can opt out by passing a ``start_tls`` value of
    ``False``.

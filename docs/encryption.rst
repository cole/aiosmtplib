.. _connection-types:

TLS, SSL & STARTTLS
===================

aiosmtplib supports the three main types of encryption used by SMTP servers:

1. Plaintext (default port 25). The connection is entirely unencrypted.
   Most authentication methods will not be supported by servers
   when using an unencrypted connection. Best suited for connecting to a
   server running locally or for testing.
2. TLS/SSL encrypted (default port 465). In this case the TLS handshake
   occurs when the connection is established, and all traffic is encrypted.
   This type of connection should generally be used where available.
3. STARTTLS (default port 587). When using STARTTLS, an initial unencrypted
   connection is made, EHLO/HELO greetings are exchanged, and the connection
   is upgraded in place once the client requests it by sending the STARTTLS
   command. Most servers require an upgrade before allowing AUTH commands.

.. tip:: By default, if aiosmtplib will connect in plaintext and upgrade the
   connetion using STARTTLS if the server supports it. If you want to opt out
   of upgrades even if the server supports them, pass a ``start_tls`` value of
   ``False``.

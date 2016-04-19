#! /usr/bin/env python3
"""SMTP client class for use with asyncio.

Author: Cole Maclean <hi@cole.io>
Based on smtplib (from the Python 3 standard library) by:
The Dragon De Monsyne <dragondm@integral.org>
"""

import re
import io
import copy
import socket
import asyncio
import logging
import email.utils
import email.generator
import base64
import hmac
from email.base64mime import body_encode as encode_base64

from .errors import (
    SMTPServerDisconnected, SMTPResponseException, SMTPConnectError,
    SMTPHeloError, SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused
)


MAX_LINE_LENGTH = 8192
SMTP_NO_CONNECTION = -1
SMTP_READY = 220
SMTP_COMPLETED = 250
SMTP_WILL_FORWARD = 251
SMTP_START_INPUT = 354
SMTP_NOT_AVAILABLE = 421

logger = logging.getLogger(__name__)


def quote_address(address_string):
    """Quote a subset of the email addresses defined by RFC 821.

    Should be able to handle anything email.utils.parseaddr can handle.
    """
    display_name, address = email.utils.parseaddr(address_string)
    if (display_name, address) == ('', ''):
        # parseaddr couldn't parse it, use it as is and hope for the best.
        if address_string.strip().startswith('<'):
            return address_string
        else:
            return "<{}>".format(address_string)
    else:
        return "<{}>".format(address)


def extract_address(address_string):
    """Extracts the email address from a display name string.

    Should be able to handle anything email.utils.parseaddr can handle.
    """
    display_name, address = email.utils.parseaddr(address_string)
    if (display_name, address) == ('', ''):
        # parseaddr couldn't parse it, so use it as is.
        return address_string
    else:
        return address


class SMTP:

    """SMTP client."""

    def __init__(self, hostname='localhost', port=25, loop=None, debug=False):
        self.hostname = hostname
        self.port = port
        self.loop = loop or asyncio.get_event_loop()
        self.debug = debug
        self.esmtp_extensions = {}
        self.last_helo_status = (None, None)
        self.reader = None
        self.writer = None
        self.ready = asyncio.Future(loop=self.loop)

        connected = asyncio.async(self.connect())
        if not self.loop.is_running():
            self.loop.run_until_complete(connected)

    @asyncio.coroutine
    def connect(self):
        """Open asyncio streams to the server and check response status.
        """
        try:
            self.reader, self.writer = yield from asyncio.open_connection(
                host=self.hostname, port=self.port)
        except (ConnectionRefusedError, OSError) as e:
            message = "Error connection to {} on port {}".format(
                self.hostname, self.port)
            raise SMTPConnectError(SMTP_NO_CONNECTION, message)

        code, message = yield from self.get_response()
        if code != SMTP_READY:
            raise SMTPConnectError(code, message)
        if self.debug:
            logger.debug("connected: %s %s", code, message)
        self.ready.set_result(True)

    @asyncio.coroutine
    def reconnect(self):
        """Clear the current connection, and start it again.
        """
        if self.ready:
            self.ready.cancel()
        if self.writer:
            self.writer.close()
        self.ready = asyncio.Future(loop=self.loop)
        yield from self.connect()

    @asyncio.coroutine
    def login(self, user, password):
        def encode_cram_md5(challenge, user, password):
            challenge = base64.b64decode(challenge)
            response = user + " " + hmac.HMAC(password.encode('ascii'),
                                              challenge, 'md5').hexdigest()
            return encode_base64(response.encode('ascii'), eol='')

        def encode_plain(user, password):
            s = "\0%s\0%s" % (user, password)
            return encode_base64(s.encode('ascii'), eol='')

        AUTH_PLAIN = "PLAIN"
        AUTH_CRAM_MD5 = "CRAM-MD5"
        AUTH_LOGIN = "LOGIN"

        yield from self.ehlo_or_helo_if_needed()

        if not self.supports("auth"):
            raise SMTPException("SMTP AUTH extension not supported by server.")

        # Authentication methods the server claims to support
        advertised_authlist = self.esmtp_extensions["auth"]

        # List of authentication methods we support: from preferred to
        # less preferred methods. Except for the purpose of testing the weaker
        # ones, we prefer stronger methods like CRAM-MD5:
        preferred_auths = [AUTH_CRAM_MD5, AUTH_PLAIN, AUTH_LOGIN]

        # We try the authentication methods the server advertises, but only the
        # ones *we* support. And in our preferred order.
        authlist = [auth for auth in preferred_auths if auth in advertised_authlist]
        if not authlist:
            raise SMTPException("No suitable authentication method found.")

        # Some servers advertise authentication methods they don't really
        # support, so if authentication fails, we continue until we've tried
        # all methods.
        for authmethod in authlist:
            if authmethod == AUTH_CRAM_MD5:
                (code, resp) = yield from self.execute_command("AUTH", AUTH_CRAM_MD5)
                if code == 334:
                    (code, resp) = yield from self.execute_command(encode_cram_md5(resp, user, password))
            elif authmethod == AUTH_PLAIN:
                (code, resp) = yield from self.execute_command("AUTH",
                    AUTH_PLAIN + " " + encode_plain(user, password))
            elif authmethod == AUTH_LOGIN:
                (code, resp) = yield from self.execute_command("AUTH",
                    "%s %s" % (AUTH_LOGIN, encode_base64(user.encode('ascii'), eol='')))
                if code == 334:
                    (code, resp) = yield from self.execute_command(encode_base64(password.encode('ascii'), eol=''))

            # 235 == 'Authentication successful'
            # 503 == 'Error: already authenticated'
            if code in (235, 503):
                return (code, resp)

        # We could not login sucessfully. Return result of last attempt.
        raise SMTPAuthenticationError(code, resp)

    @asyncio.coroutine
    def close(self):
        """Closes the connection.
        """
        yield from self.quit()
        if self.writer:
            self.writer.close()

    @property
    def is_connected(self):
        """Check connection status.

        Returns bool
        """
        return bool(self.reader) and bool(self.writer)

    @property
    def is_ready(self):
        """Check for ready message recieved from server.

        Returns bool
        """
        return self.ready.done()

    @property
    def supports_esmtp(self):
        """Check if the connection supports ESMTP.

        Returns bool
        """
        return bool(self.esmtp_extensions)

    @property
    def local_hostname(self):
        """Get the system hostname to be sent to the SMTP server.
        Simply caches the result of socket.getfqdn.
        """
        if not hasattr(self, '_local_hostname'):
            self._local_hostname = socket.getfqdn()
        return self._local_hostname

    def supports(self, extension):
        """Check if the server supports the SMTP service extension given.

        Returns bool
        """
        return extension.lower() in self.esmtp_extensions

    @asyncio.coroutine
    def get_response(self):
        """Get a status reponse from the server.

        Returns a tuple consisting of:

          - server response code (e.g. '250', or such, if all goes well)
            Note: returns -1 if it can't read response code.

          - server response string corresponding to response code (multiline
            responses are converted to a single, multiline string).

        Raises SMTPResponseException for codes > 500.
        """
        code = -1
        response = []
        while True:
            try:
                line = yield from self.reader.readline()
            except ConnectionResetError as exc:
                raise SMTPServerDisconnected(exc)

            if not line:
                break

            if len(line) > MAX_LINE_LENGTH:
                raise SMTPResponseException(500, "Line too long.")

            code = line[:3]
            message = line[4:]
            message = message.strip(b' \t\r\n')  # Strip newlines
            message = message.decode()  # Convert to string
            response.append(message)

            try:
                code = int(code)
            except ValueError:
                code = -1

            if line[3:4] != b"-":
                break

        message = "\n".join(response)
        if self.debug:
            logger.debug("reply: %s %s", code, message)
        if 500 <= code <= 599:
            raise SMTPResponseException(code, message)

        return code, message

    @asyncio.coroutine
    def send_command(self, *args):
        """Format a command and send it to the server.
        """
        command = "{}\r\n".format(' '.join(args))
        if self.debug:
            logger.debug("Sending command: %s", command)
        yield from self.send_data(command)

    @asyncio.coroutine
    def execute_command(self, *args):
        """Send the commands given and return the reply message.

        Returns (code, message) tuple.
        """
        yield from self.send_command(*args)
        result = yield from self.get_response()
        return result

    @asyncio.coroutine
    def send_data(self, data):
        if self.debug:
            logger.debug("sending data: %s", data)
        if isinstance(data, str):
            data = data.encode('ascii')

        self.writer.write(data)
        # Ensure the write finishes
        try:
            yield from self.writer.drain()
        except ConnectionResetError as exc:
            # Try a simple reconnect and resend
            try:
                yield from self.reconnect()
                yield from self.send_data(data)
            except:
                raise exc

    @asyncio.coroutine
    def helo(self, hostname=None):
        """Send the SMTP 'helo' command.
        Hostname to send for this command defaults to the FQDN of the local
        host.

        Returns a (code, message) tuple with the server response.
        """
        hostname = hostname or self.local_hostname
        code, message = yield from self.execute_command("helo", hostname)
        self.last_helo_status = (code, message)
        return code, message

    @asyncio.coroutine
    def ehlo(self, hostname=None):
        """Send the SMTP 'ehlo' command.
        Hostname to send for this command defaults to the FQDN of the local
        host.

        Returns a (code, message) tuple with the server response.
        """
        hostname = hostname or self.local_hostname
        code, message = yield from self.execute_command("ehlo", hostname)
        # According to RFC1869 some (badly written)
        # MTA's will disconnect on an ehlo. Toss an exception if
        # that happens -ddm
        if code == SMTP_NO_CONNECTION and len(message) == 0:
            self.close()
            raise SMTPServerDisconnected("Server not connected")
        elif code == SMTP_COMPLETED:
            self.parse_esmtp_response(code, message)

        self.last_helo_status = (code, message)
        return code, message

    def parse_esmtp_response(self, code, message):
        response = message.split('\n')
        # ignore the first line
        for line in response[1:]:
            # To be able to communicate with as many SMTP servers as possible,
            # we have to take the old-style auth advertisement into account,
            # because:
            # 1) Else our SMTP feature parser gets confused.
            # 2) There are some servers that only advertise the auth methods we
            #    support using the old style.
            auth_match = re.match(r"auth=(?P<auth>.*)", line, flags=re.I)
            if auth_match:
                auth_type = auth_match.group('auth')[0]
                if 'auth' not in self.esmtp_extensions:
                    self.esmtp_extensions['auth'] = []
                if auth_type not in self.esmtp_extensions['auth']:
                    self.esmtp_extensions['auth'].append(auth_type)

            # RFC 1869 requires a space between ehlo keyword and parameters.
            # It's actually stricter, in that only spaces are allowed between
            # parameters, but were not going to check for that here.  Note
            # that the space isn't present if there are no parameters.
            extensions = re.match(
                r'(?P<ext>[A-Za-z0-9][A-Za-z0-9\-]*) ?', line)
            if extensions:
                extension = extensions.group('ext').lower()
                params = extensions.string[extensions.end('ext'):].strip()
                if extension == "auth":
                    if 'auth' not in self.esmtp_extensions:
                        self.esmtp_extensions['auth'] = []
                    self.esmtp_extensions['auth'] = params.split()
                else:
                    self.esmtp_extensions[extension] = params
        if self.debug:
            logger.debug("esmtp extensions: %s", self.esmtp_extensions)

    @asyncio.coroutine
    def ehlo_or_helo_if_needed(self):
        """Call self.ehlo() and/or self.helo() if needed.

        If there has been no previous EHLO or HELO command this session, this
        method tries ESMTP EHLO first.

        This method may raise the following exceptions:

         SMTPHeloError            The server didn't reply properly to
                                  the helo greeting.
        """
        if self.last_helo_status == (None, None):
            ehlo_code, ehlo_response = yield from self.ehlo()
            if not (200 <= ehlo_code <= 299):
                helo_code, helo_response = yield from self.helo()
                if not (200 <= helo_code <= 299):
                    raise SMTPHeloError(helo_code, helo_response)

    @asyncio.coroutine
    def help(self):
        """SMTP 'help' command.
        Returns help text.
        """
        code, message = yield from self.execute_command("help")
        return message

    @asyncio.coroutine
    def rset(self):
        """Sends an SMTP 'rset' command (resets session)
        Returns a (code, message) tuple with the server response.
        """
        code, message = yield from self.execute_command("rset")
        return code, message

    @asyncio.coroutine
    def noop(self):
        """Sends an SMTP 'noop' command (does nothing)
        Returns a (code, message) tuple with the server response.
        """
        code, message = yield from self.execute_command("noop")
        return code, message

    @asyncio.coroutine
    def vrfy(self, address):
        """Sends an SMTP 'vrfy' command (tests an address for validity)
        Returns a (code, message) tuple with the server response.
        """
        address = extract_address(address)
        code, message = yield from self.execute_command("vrfy", address)
        return code, message

    @asyncio.coroutine
    def expn(self, address):
        """Sends an SMTP 'expn' command (expands a mailing list)
        Returns a (code, message) tuple with the server response.
        """
        address = extract_address(address)
        code, message = yield from self.execute_command("expn", address)
        return code, message

    @asyncio.coroutine
    def quit(self):
        """Sends the SMTP 'quit' command
        Returns a (code, message) tuple with the server response.
        """
        code, message = yield from self.execute_command("quit")
        return code, message

    @asyncio.coroutine
    def mail(self, sender, options=[]):
        """Sends the SMTP 'mail' command (begins mail transfer session)
        Returns a (code, message) tuple with the server response.

        Raises SMTPSenderRefused if the response is not 250.
        """
        from_string = "FROM:{}".format(quote_address(sender))
        code, message = yield from self.execute_command("mail", from_string,
                                                        *options)

        if code != SMTP_COMPLETED:
            if code == SMTP_NOT_AVAILABLE:
                self.close()
            else:
                # reset, raise error
                try:
                    yield from self.rset()
                except SMTPServerDisconnected:
                    pass
            raise SMTPSenderRefused(code, message, sender)

        return code, message

    @asyncio.coroutine
    def rcpt(self, recipient, options=[]):
        """Sends the SMTP 'rcpt' command (specifies a recipient for the message)
        Returns a (code, message) tuple with the server response.

        Raises SMTPRecipientsRefused on a bad status response.
        """
        to_string = "TO:{}".format(quote_address(recipient))
        errors = {}
        try:
            code, message = yield from self.execute_command("rcpt", to_string,
                                                            *options)
        except SMTPResponseException as exc:
            if 520 <= exc.smtp_code <= 599:
                errors[recipient] = (exc.smtp_code, exc.smtp_error)
            else:
                raise exc
        else:
            if code == SMTP_NOT_AVAILABLE:
                self.close()
                errors[recipient] = (code, message)

        if errors:
            raise SMTPRecipientsRefused(errors)

        return code, message

    @asyncio.coroutine
    def data(self, message):
        """Sends the SMTP 'data' command (sends message data to server)

        Automatically quotes lines beginning with a period per rfc821.
        Raises SMTPDataError if there is an unexpected reply to the
        DATA command. Lone '\r' and '\n' characters are converted to '\r\n'
        characters.

        Returns a (code, message) response tuple (the last one, after all
        data is sent.)
        """
        code, response = yield from self.execute_command("data")
        if code != SMTP_START_INPUT:
            raise SMTPDataError(code, response)

        if not isinstance(message, str):
            message = message.decode('ascii')
        message = re.sub(r'(?:\r\n|\n|\r(?!\n))', "\r\n", message)
        message = re.sub(r'(?m)^\.', '..', message)  # quote periods
        if message[-2:] != "\r\n":
            message += "\r\n"
        message += ".\r\n"
        if self.debug:
            logger.debug('message is: %s', message)

        yield from self.send_data(message)

        code, response = yield from self.get_response()
        if code != SMTP_COMPLETED:
            if code == SMTP_NOT_AVAILABLE:
                self.close()
            else:
                # reset, raise error
                try:
                    yield from self.rset()
                except SMTPServerDisconnected:
                    pass
            raise SMTPDataError(code, resp)

        return code, response

    @asyncio.coroutine
    def sendmail(self, sender, recipients, message, mail_options=[],
                 rcpt_options=[]):
        """This command performs an entire mail transaction.

        The arguments are:
            - sender       : The address sending this mail.
            - recipients   : A list of addresses to send this mail to.  A bare
                             string will be treated as a list with 1 address.
            - message      : The message string to send.
            - mail_options : List of ESMTP options (such as 8bitmime) for the
                             mail command.
            - rcpt_options : List of ESMTP options (such as DSN commands) for
                             all the rcpt commands.

        message must be a string containing characters in the ASCII range.
        The string is encoded to bytes using the ascii codec, and lone \\r and
        \\n characters are converted to \\r\\n characters.

        If there has been no previous EHLO or HELO command this session, this
        method tries ESMTP EHLO first.  If the server does ESMTP, message size
        and each of the specified options will be passed to it.  If EHLO
        fails, HELO will be tried and ESMTP options suppressed.

        This method will return normally if the mail is accepted for at least
        one recipient.  It returns a dictionary, with one entry for each
        recipient that was refused.  Each entry contains a tuple of the SMTP
        error code and the accompanying error message sent by the server.

        This method may raise the following exceptions:

         SMTPHeloError          The server didn't reply properly to
                                the helo greeting.
         SMTPRecipientsRefused  The server rejected ALL recipients
                                (no mail was sent).
         SMTPSenderRefused      The server didn't accept the from_addr.
         SMTPDataError          The server replied with an unexpected
                                error code (other than a refusal of
                                a recipient).

        Note: the connection will be open even after an exception is raised.

        Example:

         >>> import asyncio
         >>> import aiosmtplib
         >>> loop = asyncio.get_event_loop()
         >>> smtp = aiosmtplib.SMTP(hostname='localhost', port=25)
         >>> loop.run_until_complete(smtp.ready)
         >>> tolist=["one@one.org","two@two.org","three@three.org"]
         >>> msg = '''\\
         ... From: Me@my.org
         ... Subject: testin'...
         ...
         ... This is a test '''
         >>> future = asyncio.async(smtp.sendmail("me@my.org", tolist, msg))
         >>> loop.run_until_complete(future)
         >>> future.result()
         { "three@three.org" : ( 550 ,"User unknown" ) }
         >>> smtp.close()

        In the above example, the message was accepted for delivery to two
        of the three addresses, and one was rejected, with the error code
        550.  If all addresses are accepted, then the method will return an
        empty dictionary.

        """
        if isinstance(recipients, str):
            recipients = [recipients]

        esmtp_options = []
        if self.supports_esmtp:
            if self.supports('size'):
                size_option = "size={}".format(len(message))
                esmtp_options.append(size_option)
            esmtp_options = esmtp_options + mail_options

        yield from self.ehlo_or_helo_if_needed()
        code, response = yield from self.mail(sender, esmtp_options)

        # sender worked
        errors = {}
        for address in recipients:
            code, response = yield from self.rcpt(address, rcpt_options)

            if code not in (SMTP_COMPLETED, SMTP_WILL_FORWARD):
                errors[address] = (code, response)

        if len(errors) == len(recipients):
            # the server refused all our recipients
            raise SMTPRecipientsRefused(errors)

        code, response = yield from self.data(message)

        # if we got here then somebody got our mail
        return errors

    @asyncio.coroutine
    def send_message(self, message, sender=None, recipients=None,
                     mail_options=[], rcpt_options=[]):
        """Converts message to a bytestring and passes it to sendmail.

        The arguments are as for sendmail, except that messsage is an
        email.message.Message object.  If sender is None or recipients is
        None, these arguments are taken from the headers of the Message as
        described in RFC 2822 (a ValueError is raised if there is more than
        one set of 'Resent-' headers).  Regardless of the values of sender and
        recipients, any Bcc field (or Resent-Bcc field, when the Message is a
        resent) of the Message object won't be transmitted.  The Message
        object is then serialized using email.generator.BytesGenerator and
        sendmail is called to transmit the message.
        """
        # 'Resent-Date' is a mandatory field if the Message is resent (RFC 2822
        # Section 3.6.6). In such a case, we use the 'Resent-*' fields.
        # However, if there is more than one 'Resent-' block there's no way to
        # unambiguously determine which one is the most recent in all cases,
        # so rather than guess we raise a ValueError in that case.
        #
        # TODO implement heuristics to guess the correct Resent-* block with an
        # option allowing the user to enable the heuristics.  (It should be
        # possible to guess correctly almost all of the time.)

        resent = message.get_all('Resent-Date')
        if resent is None:
            header_prefix = lambda s: s
        elif len(resent) == 1:
            header_prefix = lambda s: "{}{}".format('Resent-', s)
        else:
            raise ValueError(
                "Message has more than one 'Resent-' header block")

        if not sender:
            # Prefer the sender field per RFC 2822:3.6.2.
            if header_prefix('Sender') in message:
                sender = message[header_prefix('Sender')]
            else:
                sender = message[header_prefix('From')]

        if not recipients:
            recipients = []
            address_fields = []
            for field in ('To', 'Cc', 'Bcc'):
                address_fields.extend(
                    message.get_all(header_prefix(field), []))

            for address in email.utils.getaddresses(address_fields):
                recipients.append(address)

        # Make a local copy so we can delete the bcc headers.
        message_copy = copy.copy(message)
        del message_copy['Bcc']
        del message_copy['Resent-Bcc']

        # Generate into string
        with io.BytesIO() as messageio:
            generator = email.generator.BytesGenerator(messageio)
            generator.flatten(message_copy, linesep='\r\n')
            flat_message = messageio.getvalue()

        # finally, send the message
        result = yield from self.sendmail(sender, recipients, flat_message,
                                          mail_options, rcpt_options)
        return result

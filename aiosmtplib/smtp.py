#! /usr/bin/env python3
'''SMTP client class for use with asyncio.

Author: Cole Maclean <hi@cole.io>
Based on smtplib (from the Python 3 standard library) by:
The Dragon De Monsyne <dragondm@integral.org>
'''
import io
import copy
import socket
import asyncio
import email.utils
import email.generator

from aiosmtplib import status
from aiosmtplib.streams import SMTPStreamReader, SMTPStreamWriter
from aiosmtplib.errors import (
    SMTPConnectError, SMTPHeloError, SMTPDataError, SMTPRecipientRefused,
    SMTPRecipientsRefused, SMTPSenderRefused,
)
from aiosmtplib.utils import (
    quote_address, extract_sender, extract_recipients, prepare_message_string,
)


MAX_LINE_LENGTH = 8192
SMTP_PORT = 25


class BaseSMTP:
    '''
    An SMTP client, not implementing any extensions. For those see the ESMTP
    class.
    '''

    def __init__(self, hostname='localhost', port=SMTP_PORT,
                 source_address=None, timeout=None, loop=None):
        self.hostname = hostname
        self.port = port
        self.last_helo_response = (None, None)
        self._source_address = source_address
        # TODO: implement timeout
        self.timeout = timeout

        self.reader = None
        self.writer = None
        self.protocol = None
        self.transport = None
        self.ready = asyncio.Future()
        self.loop = loop or asyncio.get_event_loop()

    async def connect(self):
        '''
        Open asyncio streams to the server and check response status.
        '''
        self.reader = SMTPStreamReader(limit=MAX_LINE_LENGTH, loop=self.loop)
        self.protocol = asyncio.StreamReaderProtocol(self.reader,
                                                     loop=self.loop)
        try:
            self.transport, _ = yield from self.loop.create_connection(
                lambda: self.protocol, self.hostname, self.port)
        except (ConnectionRefusedError, OSError):
            message = "Error connecting to {host} on port {port}".format(
                host=self.host, port=self.port)
            raise SMTPConnectError(status.SMTP_NO_CONNECTION, message)
        else:
            self.writer = SMTPStreamWriter(self.transport, self.protocol,
                                           self.reader, self.loop)

        code, message = await self.reader.read_response()
        if not status.is_success_code(code):
            raise SMTPConnectError(code, message)

        self.connected.set_result(True)

    async def close(self):
        '''
        Closes the connection.
        '''
        if self.transport:
            self.transport.close()

        self.reader = None
        self.writer = None
        self.protocol = None
        self.transport = None
        self.ready = asyncio.Future()

    @property
    def is_connected(self):
        '''
        Check connection status.

        Returns bool
        '''
        return self.transport and not self.transport.is_closing()

    @property
    def is_ready(self):
        '''
        Check for ready message recieved from server.

        Returns bool
        '''
        return self.ready.done()

    @property
    def source_address(self):
        '''
        Get the system hostname to be sent to the SMTP server.
        Simply caches the result of socket.getfqdn.
        '''
        if not self._source_address:
            self._source_address = socket.getfqdn()

        return self._source_address

    @property
    def is_helo_needed(self):
        return self.last_helo_response == (None, None)

    async def execute_command(self, *args):
        '''
        Send the commands given and return the reply message.

        Returns (code, message) tuple.
        '''
        await self.writer.send_command(*args)
        code, message = await self.reader.read_response()

        # If the server is unavailable, shut it down
        if code == status.SMTP_421_DOMAIN_UNAVAILABLE:
            await self.close()

        return code, message

    async def helo(self, hostname=None):
        '''
        Send the SMTP 'helo' command.
        Hostname to send for this command defaults to the FQDN of the local
        host.

        This method may raise the following exceptions:

         SMTPHeloError            The server didn't reply properly to
                                  the helo greeting.

        Returns a (code, message) tuple with the server response.
        '''
        hostname = hostname or self.source_address
        code, message = await self.execute_command("helo", hostname)
        self.last_helo_response = (code, message)

        if not status.is_success_code(code):
            raise SMTPHeloError(code, message)

        return code, message

    async def helo_if_needed(self):
        '''
        Call self.helo() if needed.

        This method may raise the following exceptions:

         SMTPHeloError            The server didn't reply properly to
                                  the helo greeting.
        '''
        if self.is_helo_needed:
            helo_code, helo_response = await self.helo()

    async def help(self):
        '''
        SMTP 'help' command.
        Returns help text.
        '''
        return await self.execute_command("help")

    async def rset(self):
        '''
        Sends an SMTP 'rset' command (resets session)

        Returns a (code, message) tuple with the server response.
        '''
        return await self.execute_command("rset")

    async def noop(self):
        '''
        Sends an SMTP 'noop' command (does nothing)
        Returns a (code, message) tuple with the server response.
        '''
        return await self.execute_command("noop")

    async def vrfy(self, address):
        '''
        Sends an SMTP 'vrfy' command (tests an address for validity)
        Returns a (code, message) tuple with the server response.
        '''
        parsed_address = email.utils.parseaddr(address)[1] or address
        return await self.execute_command("vrfy", parsed_address)

    async def expn(self, address):
        '''
        Sends an SMTP 'expn' command (expands a mailing list)
        Returns a (code, message) tuple with the server response.
        '''
        parsed_address = email.utils.parseaddr(address)[1] or address
        return await self.execute_command("expn", parsed_address)

    async def quit(self):
        '''
        Sends the SMTP 'quit' command, and closes the connection.
        Returns a (code, message) tuple with the server response.
        '''
        code, message = await self.execute_command("quit")
        await self.close()
        return code, message

    async def mail(self, sender, options=None):
        '''
        Sends the SMTP 'mail' command (begins mail transfer session)
        Returns a (code, message) tuple with the server response.

        Raises SMTPSenderRefused if the response is not 250.
        '''
        if options is None:
            options = []
        from_string = "FROM:{}".format(quote_address(sender))

        code, message = await self.execute_command("mail", from_string,
                                                   *options)

        if code != status.SMTP_250_COMPLETED:
            raise SMTPSenderRefused(code, message, sender)

        return code, message

    async def rcpt(self, recipient, options=None):
        '''
        Sends the SMTP 'rcpt' command (specifies a recipient for the message)
        Returns a (code, message) tuple with the server response.
        '''
        if options is None:
            options = []
        to_string = "TO:{}".format(quote_address(recipient))

        code, message = await self.execute_command("rcpt", to_string, *options)

        success_codes = (
            status.SMTP_250_COMPLETED,
            status.SMTP_251_WILL_FORWARD,
        )
        if code not in success_codes:
            raise SMTPRecipientRefused(code, message, recipient)

        return code, message

    async def data(self, message):
        '''
        Sends the SMTP 'data' command (sends message data to server)

        Raises SMTPDataError if there is an unexpected reply to the
        DATA command.

        Returns a (code, message) response tuple (the last one, after all
        data is sent.)
        '''
        code, response = await self.execute_command("data")
        if code != status.SMTP_354_START_INPUT:
            raise SMTPDataError(code, response)

        encoded_message = prepare_message_string(message)
        await self.writer.write(encoded_message)

        code, response = await self.reader.read_response()
        if code != status.SMTP_250_COMPLETED:
            raise SMTPDataError(code, response)

        return code, response

    async def sendmail(self, sender, recipients, message, mail_options=None,
                       rcpt_options=None):
        '''This command performs an entire mail transaction.

        The arguments are:
            - sender       : The address sending this mail.
            - recipients   : A list of addresses to send this mail to.  A bare
                             string will be treated as a list with 1 address.
            - message      : The message string to send.
            - mail_options : List of options (such as ESMTP 8bitmime) for the
                             mail command.
            - rcpt_options : List of options (such as DSN commands) for
                             all the rcpt commands.

        message must be a string containing characters in the ASCII range.
        The string is encoded to bytes using the ascii codec, and lone \\r and
        \\n characters are converted to \\r\\n characters.

        If there has been no previous HELO command this session, this
        method tries HELO first.

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

        # TODO: test
         >>> import asyncio
         >>> import aiosmtplib
         >>> loop = asyncio.get_event_loop()
         >>> smtp = aiosmtplib.SMTP(hostname='localhost', port=25)
         >>> loop.run_until_complete(smtp.ready)
         >>> tolist=["one@one.org","two@two.org","three@three.org"]
         >>> msg = """\\
         ... From: Me@my.org
         ... Subject: testin'...
         ...
         ... This is a test """
         >>> future = asyncio.ensure_future(
         >>>     smtp.sendmail("me@my.org", tolist, msg))
         >>> loop.run_until_complete(future)
         >>> future.result()
         { "three@three.org" : ( 550 ,"User unknown" ) }
         >>> smtp.close()

        In the above example, the message was accepted for delivery to two
        of the three addresses, and one was rejected, with the error code
        550.  If all addresses are accepted, then the method will return an
        empty dictionary.

        '''
        if isinstance(recipients, str):
            recipients = [recipients]
        if mail_options is None:
            mail_options = []
        if rcpt_options is None:
            rcpt_options = []

        await self.helo_if_needed()
        await self.mail(sender, options=mail_options)

        recipient_errors = {}
        for address in recipients:
            try:
                await self.rcpt(address, options=rcpt_options)
            except SMTPRecipientRefused as exc:
                recipient_errors[address] = (exc.code, exc.message)

        if len(recipient_errors) == len(recipients):
            raise SMTPRecipientsRefused(recipient_errors)

        await self.data(message)

        return recipient_errors or None

    async def send_message(self, message, sender=None, recipients=None,
                           mail_options=None, rcpt_options=None):
        '''
        Converts message to a bytestring and passes it to sendmail.

        The arguments are as for sendmail, except that messsage is an
        email.message.Message object.  If sender is None or recipients is
        None, these arguments are taken from the headers of the Message as
        described in RFC 2822 (a ValueError is raised if there is more than
        one set of 'Resent-' headers).  Regardless of the values of sender and
        recipients, any Bcc field (or Resent-Bcc field, when the Message is a
        resent) of the Message object won't be transmitted.  The Message
        object is then serialized using email.generator.BytesGenerator and
        sendmail is called to transmit the message.

        'Resent-Date' is a mandatory field if the Message is resent (RFC 2822
        Section 3.6.6). In such a case, we use the 'Resent-*' fields.
        However, if there is more than one 'Resent-' block there's no way to
        unambiguously determine which one is the most recent in all cases,
        so rather than guess we raise a ValueError in that case.
        '''
        resent_dates = message.get_all('Resent-Date')
        if resent_dates and len(resent_dates) > 1:
            raise ValueError(
                "Message has more than one 'Resent-' header block")

        if sender is None:
            sender = extract_sender(message, resent_dates=resent_dates)

        if recipients is None:
            recipients = extract_recipients(message, resent_dates=resent_dates)

        # Make a local copy so we can delete the bcc headers.
        message_copy = copy.copy(message)
        del message_copy['Bcc']
        del message_copy['Resent-Bcc']

        messageio = io.BytesIO()
        generator = email.generator.BytesGenerator(messageio)
        generator.flatten(message_copy, linesep='\r\n')
        flat_message = messageio.getvalue()

        result = await self.sendmail(sender, recipients, flat_message,
                                     mail_options=mail_options,
                                     rcpt_options=rcpt_options)

        return result

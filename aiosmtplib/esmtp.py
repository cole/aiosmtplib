import re

from aiosmtplib import status
from aiosmtplib.auth import AuthCramMD5, AuthPlain, AuthLogin
from aiosmtplib.smtp import BaseSMTP
from aiosmtplib.errors import (
    SMTPException, SMTPResponseException, SMTPAuthenticationError,
)


OLDSTYLE_AUTH_REGEX = re.compile(r"auth=(?P<auth>.*)", flags=re.I)
EXTENSIONS_REGEX = re.compile(r'(?P<ext>[A-Za-z0-9][A-Za-z0-9\-]*) ?')


class ESMTP(BaseSMTP):
    '''
    An ESMTP client. This is what everyone actually uses.
    '''

    # List of authentication methods we support: from preferred to
    # less preferred methods. We prefer stronger methods like CRAM-MD5.
    authentication_methods = (AuthCramMD5(), AuthPlain(), AuthLogin())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.esmtp_extensions = {}
        self.last_ehlo_response = (None, None)

    @property
    def supports_esmtp(self):
        '''
        Check if the connection supports ESMTP.

        Returns bool
        '''
        return bool(self.esmtp_extensions)

    @property
    def supported_auth_methods(self):
        if self.supports_esmtp and self.esmtp_extensions['auth']:
            supported_auth_methods = [
                auth for auth in self.authentication_methods
                if auth.extension_name in self.esmtp_extensions['auth']
            ]
        else:
            supported_auth_methods = []

        return supported_auth_methods

    @property
    def is_helo_needed(self):
        return (
            self.last_ehlo_response == (None, None) and
            self.last_helo_response == (None, None)
        )

    def supports_extension(self, extension):
        '''
        Check if the server supports the SMTP service extension given.

        Returns bool
        '''
        return extension.lower() in self.esmtp_extensions

    async def ehlo(self, hostname=None):
        '''
        Send the SMTP 'ehlo' command.
        Hostname to send for this command defaults to the FQDN of the local
        host.

        Returns a (code, message) tuple with the server response.
        '''
        hostname = hostname or self.source_address
        code, message = await self.execute_command("ehlo", hostname)

        if code == status.SMTP_250_COMPLETED:
            self.parse_esmtp_response(code, message)

        self.last_ehlo_response = (code, message)

        return code, message

    def parse_esmtp_response(self, code, message):
        '''
        Parse an ESMTP response from the server.

        It might look something like:
             220 size.does.matter.af.MIL (More ESMTP than Crappysoft!)
             EHLO heaven.af.mil
             250-size.does.matter.af.MIL offers FIFTEEN extensions:
             250-8BITMIME
             250-PIPELINING
             250-DSN
             250-ENHANCEDSTATUSCODES
             250-EXPN
             250-HELP
             250-SAML
             250-SEND
             250-SOML
             250-TURN
             250-XADR
             250-XSTA
             250-ETRN
             250-XGEN
             250 SIZE 51200000

        We add extensions in the reponse to self.esmtp_extensions.
        '''
        response_lines = message.split('\n')
        del response_lines[0]  # ignore the first line

        for line in response_lines:
            # To be able to communicate with as many SMTP servers as possible,
            # we have to take the old-style auth advertisement into account,
            # because:
            # 1) Else our SMTP feature parser gets confused.
            # 2) There are some servers that only advertise the auth methods we
            #    support using the old style.
            auth_match = OLDSTYLE_AUTH_REGEX.match(line)
            if auth_match:
                auth_type = auth_match.group('auth')[0]
                self.esmtp_extensions.setdefault('auth', [])
                if auth_type not in self.esmtp_extensions['auth']:
                    self.esmtp_extensions['auth'].append(auth_type)

            # RFC 1869 requires a space between ehlo keyword and parameters.
            # It's actually stricter, in that only spaces are allowed between
            # parameters, but were not going to check for that here.  Note
            # that the space isn't present if there are no parameters.
            extensions = EXTENSIONS_REGEX.match(line)
            if extensions:
                extension = extensions.group('ext').lower()
                params = extensions.string[extensions.end('ext'):].strip()
                if extension == "auth":
                    self.esmtp_extensions.setdefault('auth', [])
                    self.esmtp_extensions['auth'] += params.split()
                else:
                    self.esmtp_extensions[extension] = params

    async def helo_if_needed(self):
        '''
        Call self.ehlo() and/or self.helo() if needed.

        If there has been no previous EHLO or HELO command this session, this
        method tries ESMTP EHLO first.

        This method may raise the following exceptions:

         SMTPHeloError            The server didn't reply properly to
                                  the helo greeting.
        '''
        if self.is_helo_needed:
            try:
                ehlo_code, ehlo_response = await self.ehlo()
            except SMTPResponseException as exc:
                ehlo_code, ehlo_response = exc.code, exc.message

            if not status.is_success_code(ehlo_code):
                helo_code, helo_response = await self.helo()

    async def _auth(self, auth_method, username, password):
        '''
        Try a single auth method. Used as part of login.
        '''
        request_command = auth_method.encode_request(username, password)
        code, response = await self.execute_command('AUTH', request_command)
        if code == status.SMTP_334_AUTH_CONTINUE:
            next_command = auth_method.encode_verification(code, response,
                                                           username, password)
            if next_command:
                code, response = await self.execute_command(next_command)

        return code, response

    async def login(self, username, password):
        await self.helo_if_needed()

        if not self.supports("auth"):
            raise SMTPException("SMTP AUTH extension not supported by server.")

        if not self.supported_auth_methods:
            raise SMTPException("No suitable authentication method found.")

        # Some servers advertise authentication methods they don't really
        # support, so if authentication fails, we continue until we've tried
        # all methods.
        for auth_method in self.supported_auth_methods:
            try:
                code, message = self._auth(auth_method, username, password)
            except SMTPResponseException as exc:
                # In this context, 503 means we're already authenticated.
                # Ignore.
                if exc.code == status.SMTP_503_BAD_COMMAND_SEQUENCE:
                    return exc.code, exc.message
                else:
                    raise exc
            else:
                if code == status.SMTP_235_AUTH_SUCCESSFUL:
                    return code, message

        # We could not login sucessfully. Return result of last attempt.
        raise SMTPAuthenticationError(code, message)

    async def sendmail(self, sender, recipients, message, mail_options=None,
                       rcpt_options=None):
        '''This command performs an entire mail transaction.

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
        if mail_options is None:
            mail_options = []

        if self.supports_esmtp and self.supports_extension('size'):
            size_option = "size={}".format(len(message))
            mail_options.append(size_option)

        return super().sendmail(sender, recipients, message,
                                mail_options=mail_options,
                                rcpt_options=rcpt_options)

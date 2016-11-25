import re
import email.utils
from email.base64mime import body_encode, body_decode


LINE_ENDINGS_REGEX = re.compile(b'(?:\r\n|\n|\r(?!\n))')
PERIOD_REGEX = re.compile(b'(?m)^\.')
OLDSTYLE_AUTH_REGEX = re.compile(r'auth=(?P<auth>.*)', flags=re.I)
EXTENSIONS_REGEX = re.compile(r'(?P<ext>[A-Za-z0-9][A-Za-z0-9\-]*) ?')


def b64_encode(text):
    return body_encode(text.encode('utf-8'), eol='')


def b64_decode(text):
    return body_decode(text).decode('utf-8')


def quote_address(address):
    '''
    Quote a subset of the email addresses defined by RFC 821.

    Should be able to handle anything email.utils.parseaddr can handle.
    '''
    display_name, parsed_address = email.utils.parseaddr(address)
    if parsed_address:
        quoted_address = '<{}>'.format(parsed_address)
    # parseaddr couldn't parse it, use it as is and hope for the best.
    elif address.lstrip().startswith('<'):
        quoted_address = address.strip()
    else:
        quoted_address = '<{}>'.format(address.strip())

    return quoted_address


def extract_sender(message, resent_dates=None):
    '''
    Returns a sender pulled from the email message object (using appropriate
    headers).
    '''
    if not resent_dates:
        sender_header = 'Sender'
        from_header = 'From'
    else:
        sender_header = 'Resent-Sender'
        from_header = 'Resent-From'

    # Prefer the sender field per RFC 2822:3.6.2.
    if sender_header in message:
        sender = message[sender_header]
    else:
        sender = message[from_header]

    return sender


def extract_recipients(message, resent_dates=None):
    '''
    Returns a list of recipients pulled from the email message object
    (using appropriate headers).
    '''
    recipients = []

    if not resent_dates:
        recipient_headers = ('To', 'Cc', 'Bcc')
    else:
        recipient_headers = ('Resent-To', 'Resent-Cc', 'Resent-Bcc')

    for header in recipient_headers:
        recipients.extend(message.get_all(header, []))

    parsed_recipients = email.utils.getaddresses(recipients)

    return parsed_recipients


def encode_message_string(message_str):
    '''
    Prepare a message for sending.
    Automatically quotes lines beginning with a period per RFC821.
    Lone '\r' and '\n' characters are converted to '\r\n' characters.

    Returns bytes.
    '''
    if isinstance(message_str, bytes):
        message_bytes = message_str
    else:
        message_bytes = message_str.encode('utf-8')
    message_bytes = LINE_ENDINGS_REGEX.sub(b'\r\n', message_bytes)
    message_bytes = PERIOD_REGEX.sub(b'..', message_bytes)
    if not message_bytes.endswith(b'\r\n'):
        message_bytes += b'\r\n'
    message_bytes += b'.\r\n'

    return message_bytes


def parse_esmtp_extensions(message):
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

    Returns a tuple containing:
        a dict of extension names to values (pretty much only size has a value)
        a list of auth methods supported
    '''
    esmtp_extensions = {}
    auth_types = []

    response_lines = message.split('\n')

    # ignore the first line
    for line in response_lines[1:]:
        # To be able to communicate with as many SMTP servers as possible,
        # we have to take the old-style auth advertisement into account,
        # because:
        # 1) Else our SMTP feature parser gets confused.
        # 2) There are some servers that only advertise the auth methods we
        #    support using the old style.
        auth_match = OLDSTYLE_AUTH_REGEX.match(line)
        if auth_match:
            auth_type = auth_match.group('auth')[0]
            if auth_type not in auth_types:
                auth_types.append(auth_type.lower().strip())

        # RFC 1869 requires a space between ehlo keyword and parameters.
        # It's actually stricter, in that only spaces are allowed between
        # parameters, but were not going to check for that here.  Note
        # that the space isn't present if there are no parameters.
        extensions = EXTENSIONS_REGEX.match(line)
        if extensions:
            extension = extensions.group('ext').lower()
            params = extensions.string[extensions.end('ext'):].strip()
            esmtp_extensions[extension] = params

            if extension == 'auth':
                auth_types.extend(
                    [param.strip().lower() for param in params.split()])

    return esmtp_extensions, auth_types

import re
import email.utils


def quote_address(address):
    '''
    Quote a subset of the email addresses defined by RFC 821.

    Should be able to handle anything email.utils.parseaddr can handle.
    '''
    display_name, parsed_address = email.utils.parseaddr(address)
    if parsed_address:
        quoted_address = "<{}>".format(parsed_address)
    # parseaddr couldn't parse it, use it as is and hope for the best.
    elif address.lstrip().startswith('<'):
        quoted_address = address.strip()
    else:
        quoted_address = "<{}>".format(address.strip())

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
        address_field_values = message.get_all(header, [])
        for raw_address in address_field_values:
            recipient = email.utils.getaddresses(raw_address)
            recipients.append(recipient)

    return recipients


def prepare_message_string(message_str):
    '''
    Prepare a message for sending.
    Automatically quotes lines beginning with a period per RFC821.
    Lone '\r' and '\n' characters are converted to '\r\n' characters.

    Returns bytes.
    '''
    message_bytes = message_str.encode('utf-8')
    message_bytes = re.sub(r'(?:\r\n|\n|\r(?!\n))', b"\r\n", message_bytes)
    message_bytes = re.sub(r'(?m)^\.', b'..', message_bytes)
    if not message_bytes.endswith(b"\r\n"):
        message_bytes += b"\r\n"
    message_bytes += b".\r\n"

    return message_bytes

"""
Email message and address formatting/parsing functions.
"""
import copy
import email.charset
import email.generator
import email.header
import email.headerregistry
import email.message
import email.policy
import email.utils
import io
import re
from typing import List, Optional, Tuple, Union


__all__ = (
    "extract_recipients",
    "extract_sender",
    "flatten_message",
    "parse_address",
    "quote_address",
)


LINE_SEP = "\r\n"
SPECIALS_REGEX = re.compile(r'[][\\()<>@,:;".]')
ESCAPES_REGEX = re.compile(r'[\\"]')
UTF8_CHARSET = email.charset.Charset("utf-8")


def parse_address(address: str) -> str:
    """
    Parse an email address, falling back to the raw string given.
    """
    display_name, parsed_address = email.utils.parseaddr(address)

    return parsed_address or address.strip()


def quote_address(address: str) -> str:
    """
    Quote a subset of the email addresses defined by RFC 821.
    """
    parsed_address = parse_address(address)
    return f"<{parsed_address}>"


def formataddr(pair: Tuple[str, str]) -> str:
    """
    Copied from the standard library, and modified to handle international (UTF-8)
    email addresses.

    The inverse of parseaddr(), this takes a 2-tuple of the form
    (realname, email_address) and returns the string value suitable
    for an RFC 2822 From, To or Cc header.
    If the first element of pair is false, then the second element is
    returned unmodified.
    """
    name, address = pair
    if name:
        encoded_name = UTF8_CHARSET.header_encode(name)
        return f"{encoded_name} <{address}>"
    else:
        quotes = ""
        if SPECIALS_REGEX.search(name):
            quotes = '"'
            name = ESCAPES_REGEX.sub(r"\\\g<0>", name)
            return f"{quotes}{name}{quotes} <{address}>"

    return address


def flatten_message(
    message: Union[email.message.EmailMessage, email.message.Message],
    utf8: bool = False,
    cte_type: str = "8bit",
) -> bytes:
    # Make a local copy so we can delete the bcc headers.
    message_copy = copy.copy(message)
    del message_copy["Bcc"]
    del message_copy["Resent-Bcc"]

    if isinstance(message, email.message.EmailMessage):
        # New message class, default policy
        policy = email.policy.default.clone(
            linesep=LINE_SEP,
            utf8=utf8,
            cte_type=cte_type,
        )
    else:
        # Old message class, Compat32 policy.
        # Compat32 cannot use UTF8
        policy = email.policy.compat32.clone(linesep=LINE_SEP, cte_type=cte_type)

    with io.BytesIO() as messageio:
        generator = email.generator.BytesGenerator(messageio, policy=policy)
        generator.flatten(message_copy)
        flat_message = messageio.getvalue()

    return flat_message


def extract_addresses(
    header: Union[str, email.headerregistry.AddressHeader, email.header.Header],
) -> List[str]:
    """
    Convert address headers into raw email addresses, suitable for use in
    low level SMTP commands.
    """
    addresses = []
    if isinstance(header, email.headerregistry.AddressHeader):
        for address in header.addresses:
            # If the object has been assigned an iterable, it's possible to get
            # a string here
            if isinstance(address, email.headerregistry.Address):
                addresses.append(address.addr_spec)
            else:
                addresses.append(parse_address(address))
    elif isinstance(header, email.header.Header):
        for address_bytes, charset in email.header.decode_header(header):
            if charset is None:
                charset = "ascii"
            addresses.append(parse_address(str(address_bytes, encoding=charset)))
    else:
        addresses.extend(addr for _, addr in email.utils.getaddresses([header]))

    return addresses


def extract_sender(
    message: Union[email.message.EmailMessage, email.message.Message]
) -> Optional[str]:
    """
    Extract the sender from the message object given.
    """
    resent_dates = message.get_all("Resent-Date")

    if resent_dates is not None and len(resent_dates) > 1:
        raise ValueError("Message has more than one 'Resent-' header block")
    elif resent_dates:
        sender_header_name = "Resent-Sender"
        from_header_name = "Resent-From"
    else:
        sender_header_name = "Sender"
        from_header_name = "From"

    # Prefer the sender field per RFC 2822:3.6.2.
    if sender_header_name in message:
        sender_header = message[sender_header_name]
    else:
        sender_header = message[from_header_name]

    if sender_header is None:
        return None

    return extract_addresses(sender_header)[0]


def extract_recipients(
    message: Union[email.message.EmailMessage, email.message.Message]
) -> List[str]:
    """
    Extract the recipients from the message object given.
    """
    recipients: List[str] = []

    resent_dates = message.get_all("Resent-Date")

    if resent_dates is not None and len(resent_dates) > 1:
        raise ValueError("Message has more than one 'Resent-' header block")
    elif resent_dates:
        recipient_headers = ("Resent-To", "Resent-Cc", "Resent-Bcc")
    else:
        recipient_headers = ("To", "Cc", "Bcc")

    for header in recipient_headers:
        for recipient in message.get_all(header, failobj=[]):
            recipients.extend(extract_addresses(recipient))

    return recipients

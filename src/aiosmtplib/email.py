"""
Email message and address formatting/parsing functions.
"""
import copy
import email.generator
import email.policy
import email.utils
import io
from email.message import Message
from typing import List


__all__ = ("flatten_message", "parse_address", "quote_address")


def parse_address(address: str) -> str:
    """
    Parse an email address, falling back to the raw string given.
    """
    display_name, parsed_address = email.utils.parseaddr(address)

    return parsed_address or address


def quote_address(address: str) -> str:
    """
    Quote a subset of the email addresses defined by RFC 821.

    Should be able to handle anything email.utils.parseaddr can handle.
    """
    display_name, parsed_address = email.utils.parseaddr(address)
    if parsed_address:
        quoted_address = "<{}>".format(parsed_address)
    # parseaddr couldn't parse it, use it as is and hope for the best.
    else:
        quoted_address = "<{}>".format(address.strip())

    return quoted_address


def flatten_message(
    message: Message, utf8: bool = False, cte_type: str = "8bit"
) -> bytes:
    # Make a local copy so we can delete the bcc headers.
    message_copy = copy.copy(message)
    del message_copy["Bcc"]
    del message_copy["Resent-Bcc"]

    if utf8:
        policy = email.policy.SMTPUTF8  # type: email.policy.Policy
    else:
        policy = email.policy.SMTP

    if policy.cte_type != cte_type:
        policy = policy.clone(cte_type=cte_type)

    with io.BytesIO() as messageio:
        generator = email.generator.BytesGenerator(  # type: ignore
            messageio, policy=policy
        )
        generator.flatten(message_copy)
        flat_message = messageio.getvalue()

    return flat_message


def extract_sender(message: Message) -> str:
    """
    Extract the sender from the message object given.
    """
    resent_dates = message.get_all("Resent-Date")

    if resent_dates is not None and len(resent_dates) > 1:
        raise ValueError("Message has more than one 'Resent-' header block")
    elif resent_dates:
        sender_header = "Resent-Sender"
        from_header = "Resent-From"
    else:
        sender_header = "Sender"
        from_header = "From"

    # Prefer the sender field per RFC 2822:3.6.2.
    if sender_header in message:
        sender = message[sender_header]
    else:
        sender = message[from_header]

    if sender is None:
        sender = ""

    return str(sender)


def extract_recipients(message: Message) -> List[str]:
    """
    Extract the recipients from the message object given.
    """
    recipients = []  # type: List[str]

    resent_dates = message.get_all("Resent-Date")

    if resent_dates is not None and len(resent_dates) > 1:
        raise ValueError("Message has more than one 'Resent-' header block")
    elif resent_dates:
        recipient_headers = ("Resent-To", "Resent-Cc", "Resent-Bcc")
    else:
        recipient_headers = ("To", "Cc", "Bcc")

    for header in recipient_headers:
        for recipient in message.get_all(header, failobj=[]):
            recipients.append(str(recipient))

    parsed_recipients = [
        str(email.utils.formataddr(address))
        for address in email.utils.getaddresses(recipients)
    ]

    return parsed_recipients

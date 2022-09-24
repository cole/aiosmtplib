"""
Test message and address parsing/formatting functions.
"""
from email.header import Header
from email.headerregistry import Address
from email.message import EmailMessage, Message
from typing import List, Union

import pytest
from hypothesis import example, given
from hypothesis.strategies import emails

from aiosmtplib.email import (
    extract_recipients,
    extract_sender,
    flatten_message,
    parse_address,
    quote_address,
)


@pytest.mark.parametrize(
    "address, expected_address",
    (
        ('"A.Smith" <asmith+foo@example.com>', "asmith+foo@example.com"),
        ("Pepé Le Pew <pépe@example.com>", "pépe@example.com"),
        ("<a@new.topleveldomain>", "a@new.topleveldomain"),
        ("B. Smith <b@example.com", "b@example.com"),
    ),
    ids=("quotes", "nonascii", "newtld", "missing_end_<"),
)
def test_parse_address_with_display_names(address: str, expected_address: str) -> None:
    parsed_address = parse_address(address)
    assert parsed_address == expected_address


@given(emails())
@example("email@[123.123.123.123]")
@example("_______@example.com")
def test_parse_address(email: str) -> None:
    assert parse_address(email) == email


@pytest.mark.parametrize(
    "address, expected_address",
    (
        ('"A.Smith" <asmith+foo@example.com>', "<asmith+foo@example.com>"),
        ("Pepé Le Pew <pépe@example.com>", "<pépe@example.com>"),
        ("<a@new.topleveldomain>", "<a@new.topleveldomain>"),
        ("email@[123.123.123.123]", "<email@[123.123.123.123]>"),
        ("_______@example.com", "<_______@example.com>"),
        ("B. Smith <b@example.com", "<b@example.com>"),
    ),
    ids=("quotes", "nonascii", "newtld", "ipaddr", "underscores", "missing_end_quote"),
)
def test_quote_address_with_display_names(address: str, expected_address: str) -> None:
    quoted_address = quote_address(address)
    assert quoted_address == expected_address


@given(emails())
@example("email@[123.123.123.123]")
@example("_______@example.com")
def test_quote_address(email: str) -> None:
    assert quote_address(email) == f"<{email}>"


def test_flatten_message() -> None:
    message = EmailMessage()
    message["To"] = "bob@example.com"
    message["Subject"] = "Hello, World."
    message["From"] = "alice@example.com"
    message.set_content("This is a test")

    flat_message = flatten_message(message)

    expected_message = b"""To: bob@example.com\r
Subject: Hello, World.\r
From: alice@example.com\r
Content-Type: text/plain; charset="utf-8"\r
Content-Transfer-Encoding: 7bit\r
MIME-Version: 1.0\r
\r
This is a test\r
"""
    assert flat_message == expected_message


@pytest.mark.parametrize(
    "utf8, cte_type, expected_chunk",
    (
        (False, "7bit", b"=?utf-8?q?=C3=A5lice?="),
        (True, "7bit", b"From: \xc3\xa5lice@example.com"),
        (False, "8bit", b"=?utf-8?q?=C3=A5lice?="),
        (True, "8bit", b"\xc3\xa5lice@example.com"),
    ),
    ids=("ascii-7bit", "utf8-7bit", "ascii-8bit", "utf8-8bit"),
)
def test_flatten_message_utf8_options(
    utf8: bool, cte_type: str, expected_chunk: bytes
) -> None:
    message = EmailMessage()
    message["From"] = "ålice@example.com"

    flat_message = flatten_message(message, utf8=utf8, cte_type=cte_type)

    assert expected_chunk in flat_message


def test_flatten_message_removes_bcc_from_message_text() -> None:
    message = EmailMessage()
    message["Bcc"] = "alice@example.com"

    flat_message = flatten_message(message)

    assert flat_message == b"\r\n"  # empty message


def test_flatten_resent_message() -> None:
    message = EmailMessage()
    message["To"] = "bob@example.com"
    message["Cc"] = "claire@example.com"
    message["Bcc"] = "dustin@example.com"

    message["Subject"] = "Hello, World."
    message["From"] = "alice@example.com"
    message.set_content("This is a test")

    message["Resent-Date"] = "Mon, 20 Nov 2017 21:04:27 -0000"
    message["Resent-To"] = "eliza@example.com"
    message["Resent-Cc"] = "fred@example.com"
    message["Resent-Bcc"] = "gina@example.com"
    message["Resent-Subject"] = "Fwd: Hello, World."
    message["Resent-From"] = "hubert@example.com"

    flat_message = flatten_message(message)

    expected_message = b"""To: bob@example.com\r
Cc: claire@example.com\r
Subject: Hello, World.\r
From: alice@example.com\r
Content-Type: text/plain; charset="utf-8"\r
Content-Transfer-Encoding: 7bit\r
MIME-Version: 1.0\r
Resent-Date: Mon, 20 Nov 2017 21:04:27 -0000\r
Resent-To: eliza@example.com\r
Resent-Cc: fred@example.com\r
Resent-Subject: Fwd: Hello, World.\r
Resent-From: hubert@example.com\r
\r
This is a test\r
"""
    assert flat_message == expected_message


@pytest.mark.parametrize(
    "mime_to_header,mime_cc_header,compat32_to_header,"
    "compat32_cc_header,expected_recipients",
    (
        (
            "Alice Smith <alice@example.com>, hackerman@email.com",
            "Bob <Bob@example.com>",
            "Alice Smith <alice@example.com>, hackerman@email.com",
            "Bob <Bob@example.com>",
            ["alice@example.com", "hackerman@email.com", "Bob@example.com"],
        ),
        (
            Address(display_name="Alice Smith", username="alice", domain="example.com"),
            Address(display_name="Bob", username="Bob", domain="example.com"),
            Header("Alice Smith <alice@example.com>"),
            Header("Bob <Bob@example.com>"),
            ["alice@example.com", "Bob@example.com"],
        ),
        (
            Address(display_name="ålice Smith", username="ålice", domain="example.com"),
            Address(display_name="Bøb", username="Bøb", domain="example.com"),
            Header("ålice Smith <ålice@example.com>"),
            Header("Bøb <Bøb@example.com>"),
            ["ålice@example.com", "Bøb@example.com"],
        ),
        (
            Address(display_name="ålice Smith", username="alice", domain="example.com"),
            Address(display_name="Bøb", username="Bob", domain="example.com"),
            Header("ålice Smith <alice@example.com>"),
            Header("Bøb <Bob@example.com>"),
            ["alice@example.com", "Bob@example.com"],
        ),
    ),
    ids=("str", "ascii", "utf8_address", "utf8_display_name"),
)
def test_extract_recipients(
    mime_to_header: Union[str, Address],
    mime_cc_header: Union[str, Address],
    compat32_to_header: Union[str, Header],
    compat32_cc_header: Union[str, Header],
    expected_recipients: List[str],
) -> None:
    mime_message = EmailMessage()
    mime_message["To"] = mime_to_header
    mime_message["Cc"] = mime_cc_header

    mime_recipients = extract_recipients(mime_message)

    assert mime_recipients == expected_recipients

    compat32_message = Message()
    compat32_message["To"] = compat32_to_header
    compat32_message["Cc"] = compat32_cc_header

    compat32_recipients = extract_recipients(compat32_message)

    assert compat32_recipients == expected_recipients


def test_extract_recipients_includes_bcc() -> None:
    message = EmailMessage()
    message["Bcc"] = "alice@example.com"

    recipients = extract_recipients(message)

    assert recipients == [message["Bcc"]]


def test_extract_recipients_invalid_email() -> None:
    message = EmailMessage()
    message["Cc"] = "me"

    recipients = extract_recipients(message)

    assert recipients == ["me"]


def test_extract_recipients_with_iterable_of_strings() -> None:
    message = EmailMessage()
    message["To"] = ("me@example.com", "you")

    recipients = extract_recipients(message)

    assert recipients == ["me@example.com", "you"]


def test_extract_recipients_resent_message() -> None:
    message = EmailMessage()
    message["To"] = "bob@example.com"
    message["Cc"] = "claire@example.com"
    message["Bcc"] = "dustin@example.com"

    message["Resent-Date"] = "Mon, 20 Nov 2017 21:04:27 -0000"
    message["Resent-To"] = "eliza@example.com"
    message["Resent-Cc"] = "fred@example.com"
    message["Resent-Bcc"] = "gina@example.com"

    recipients = extract_recipients(message)

    assert message["Resent-To"] in recipients
    assert message["Resent-Cc"] in recipients
    assert message["Resent-Bcc"] in recipients
    assert message["To"] not in recipients
    assert message["Cc"] not in recipients
    assert message["Bcc"] not in recipients


def test_extract_recipients_valueerror_on_multiple_resent_message() -> None:
    message = EmailMessage()
    message["Resent-Date"] = "Mon, 20 Nov 2016 21:04:27 -0000"
    message["Resent-Date"] = "Mon, 20 Nov 2017 21:04:27 -0000"

    with pytest.raises(ValueError):
        extract_recipients(message)


@pytest.mark.parametrize(
    "mime_header,compat32_header,expected_sender",
    (
        (
            "Alice Smith <alice@example.com>",
            "Alice Smith <alice@example.com>",
            "alice@example.com",
        ),
        (
            Address(display_name="Alice Smith", username="alice", domain="example.com"),
            Header("Alice Smith <alice@example.com>"),
            "alice@example.com",
        ),
        (
            Address(display_name="ålice Smith", username="ålice", domain="example.com"),
            Header("ålice Smith <ålice@example.com>", "utf-8"),
            "ålice@example.com",
        ),
        (
            Address(display_name="ålice Smith", username="alice", domain="example.com"),
            Header("ålice Smith <alice@example.com>", "utf-8"),
            "alice@example.com",
        ),
    ),
    ids=("str", "ascii", "utf8_address", "utf8_display_name"),
)
def test_extract_sender(
    mime_header: Union[str, Address],
    compat32_header: Union[str, Header],
    expected_sender: str,
) -> None:
    mime_message = EmailMessage()
    mime_message["From"] = mime_header

    mime_sender = extract_sender(mime_message)

    assert mime_sender == expected_sender

    compat32_message = Message()
    compat32_message["From"] = compat32_header

    compat32_sender = extract_sender(compat32_message)

    assert compat32_sender == expected_sender


def test_extract_sender_prefers_sender_header() -> None:
    message = EmailMessage()
    message["From"] = "bob@example.com"
    message["Sender"] = "alice@example.com"

    sender = extract_sender(message)

    assert sender != message["From"]
    assert sender == message["Sender"]


def test_extract_sender_resent_message() -> None:
    message = EmailMessage()
    message["From"] = "alice@example.com"

    message["Resent-Date"] = "Mon, 20 Nov 2017 21:04:27 -0000"
    message["Resent-From"] = "hubert@example.com"

    sender = extract_sender(message)

    assert sender == message["Resent-From"]
    assert sender != message["From"]


def test_extract_sender_valueerror_on_multiple_resent_message() -> None:
    message = EmailMessage()
    message["Resent-Date"] = "Mon, 20 Nov 2016 21:04:27 -0000"
    message["Resent-Date"] = "Mon, 20 Nov 2017 21:04:27 -0000"

    with pytest.raises(ValueError):
        extract_sender(message)

"""
Test error class imports, arguments, and inheritance.
"""
import asyncio

import pytest
from hypothesis import given
from hypothesis.strategies import integers, lists, text

from aiosmtplib import (
    SMTPAuthenticationError,
    SMTPConnectError,
    SMTPConnectTimeoutError,
    SMTPDataError,
    SMTPException,
    SMTPHeloError,
    SMTPNotSupported,
    SMTPReadTimeoutError,
    SMTPRecipientRefused,
    SMTPRecipientsRefused,
    SMTPResponseException,
    SMTPSenderRefused,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)


@given(text())
def test_raise_smtp_exception(message):
    with pytest.raises(SMTPException) as excinfo:
        raise SMTPException(message)

    assert excinfo.value.message == message


@given(integers(), text())
def test_raise_smtp_response_exception(code, message):
    with pytest.raises(SMTPResponseException) as excinfo:
        raise SMTPResponseException(code, message)

    assert issubclass(excinfo.type, SMTPException)
    assert excinfo.value.code == code
    assert excinfo.value.message == message


@pytest.mark.parametrize(
    "error_class", (SMTPServerDisconnected, SMTPConnectError, SMTPConnectTimeoutError)
)
@given(message=text())
def test_connection_exceptions(message, error_class):
    with pytest.raises(error_class) as excinfo:
        raise error_class(message)

    assert issubclass(excinfo.type, SMTPException)
    assert issubclass(excinfo.type, ConnectionError)
    assert excinfo.value.message == message


@pytest.mark.parametrize(
    "error_class", (SMTPTimeoutError, SMTPConnectTimeoutError, SMTPReadTimeoutError)
)
@given(message=text())
def test_timeout_exceptions(message, error_class):
    with pytest.raises(error_class) as excinfo:
        raise error_class(message)

    assert issubclass(excinfo.type, SMTPException)
    assert issubclass(excinfo.type, asyncio.TimeoutError)
    assert excinfo.value.message == message


@pytest.mark.parametrize(
    "error_class", (SMTPHeloError, SMTPDataError, SMTPAuthenticationError)
)
@given(code=integers(), message=text())
def test_simple_response_exceptions(code, message, error_class):
    with pytest.raises(error_class) as excinfo:
        raise error_class(code, message)

    assert issubclass(excinfo.type, SMTPResponseException)
    assert excinfo.value.code == code
    assert excinfo.value.message == message


@given(integers(), text(), text())
def test_raise_smtp_sender_refused(code, message, sender):
    with pytest.raises(SMTPSenderRefused) as excinfo:
        raise SMTPSenderRefused(code, message, sender)

    assert issubclass(excinfo.type, SMTPResponseException)
    assert excinfo.value.code == code
    assert excinfo.value.message == message
    assert excinfo.value.sender == sender


@given(integers(), text(), text())
def test_raise_smtp_recipient_refused(code, message, recipient):
    with pytest.raises(SMTPRecipientRefused) as excinfo:
        raise SMTPRecipientRefused(code, message, recipient)

    assert issubclass(excinfo.type, SMTPResponseException)
    assert excinfo.value.code == code
    assert excinfo.value.message == message
    assert excinfo.value.recipient == recipient


@given(lists(elements=text()))
def test_raise_smtp_recipients_refused(addresses):
    with pytest.raises(SMTPRecipientsRefused) as excinfo:
        raise SMTPRecipientsRefused(addresses)

    assert issubclass(excinfo.type, SMTPException)
    assert excinfo.value.recipients == addresses


@given(message=text())
def test_raise_smtp_not_supported(message):
    with pytest.raises(SMTPNotSupported) as excinfo:
        raise SMTPNotSupported(message)

    assert issubclass(excinfo.type, SMTPException)
    assert excinfo.value.message == message

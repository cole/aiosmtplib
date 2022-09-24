"""
Test error class imports, arguments, and inheritance.
"""
import asyncio
from typing import List, Tuple, Type, Union

import pytest
from hypothesis import given
from hypothesis.strategies import integers, lists, text, tuples

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


@given(error_message=text())
def test_raise_smtp_exception(error_message: str) -> None:
    with pytest.raises(SMTPException) as excinfo:
        raise SMTPException(error_message)

    assert excinfo.value.message == error_message


@given(code=integers(), error_message=text())
def test_raise_smtp_response_exception(code: int, error_message: str) -> None:
    with pytest.raises(SMTPResponseException) as excinfo:
        raise SMTPResponseException(code, error_message)

    assert issubclass(excinfo.type, SMTPException)
    assert excinfo.value.code == code
    assert excinfo.value.message == error_message


@pytest.mark.parametrize(
    "error_class", (SMTPServerDisconnected, SMTPConnectError, SMTPConnectTimeoutError)
)
@given(error_message=text())
def test_connection_exceptions(
    error_message: str, error_class: Type[SMTPException]
) -> None:
    with pytest.raises(error_class) as excinfo:
        raise error_class(error_message)

    assert issubclass(excinfo.type, SMTPException)
    assert issubclass(excinfo.type, ConnectionError)
    assert excinfo.value.message == error_message


@pytest.mark.parametrize(
    "error_class", (SMTPTimeoutError, SMTPConnectTimeoutError, SMTPReadTimeoutError)
)
@given(error_message=text())
def test_timeout_exceptions(
    error_message: str, error_class: Type[SMTPException]
) -> None:
    with pytest.raises(error_class) as excinfo:
        raise error_class(error_message)

    assert issubclass(excinfo.type, SMTPException)
    assert issubclass(excinfo.type, asyncio.TimeoutError)
    assert excinfo.value.message == error_message


@pytest.mark.parametrize(
    "error_class", (SMTPHeloError, SMTPDataError, SMTPAuthenticationError)
)
@given(code=integers(), error_message=text())
def test_simple_response_exceptions(
    code: int,
    error_message: str,
    error_class: Type[Union[SMTPHeloError, SMTPDataError, SMTPAuthenticationError]],
) -> None:
    with pytest.raises(error_class) as excinfo:
        raise error_class(code, error_message)

    assert issubclass(excinfo.type, SMTPResponseException)
    assert excinfo.value.code == code
    assert excinfo.value.message == error_message


@given(code=integers(), error_message=text(), sender=text())
def test_raise_smtp_sender_refused(code: int, error_message: str, sender: str) -> None:
    with pytest.raises(SMTPSenderRefused) as excinfo:
        raise SMTPSenderRefused(code, error_message, sender)

    assert issubclass(excinfo.type, SMTPResponseException)
    assert excinfo.value.code == code
    assert excinfo.value.message == error_message
    assert excinfo.value.sender == sender


@given(code=integers(), error_message=text(), recipient=text())
def test_raise_smtp_recipient_refused(
    code: int, error_message: str, recipient: str
) -> None:
    with pytest.raises(SMTPRecipientRefused) as excinfo:
        raise SMTPRecipientRefused(code, error_message, recipient)

    assert issubclass(excinfo.type, SMTPResponseException)
    assert excinfo.value.code == code
    assert excinfo.value.message == error_message
    assert excinfo.value.recipient == recipient


@given(lists(elements=tuples(integers(), text(), text())))
def test_raise_smtp_recipients_refused(addresses: List[Tuple[int, str, str]]) -> None:
    errors = [SMTPRecipientRefused(*address) for address in addresses]
    with pytest.raises(SMTPRecipientsRefused) as excinfo:
        raise SMTPRecipientsRefused(errors)

    assert issubclass(excinfo.type, SMTPException)
    assert excinfo.value.recipients == errors


@given(error_message=text())
def test_raise_smtp_not_supported(error_message: str) -> None:
    with pytest.raises(SMTPNotSupported) as excinfo:
        raise SMTPNotSupported(error_message)

    assert issubclass(excinfo.type, SMTPException)
    assert excinfo.value.message == error_message

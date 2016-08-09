'''
Test error class imports, arguments, and inheritance
'''
import pytest

from aiosmtplib import (
    SMTPException, SMTPServerDisconnected, SMTPConnectError,
    SMTPResponseException, SMTPNotSupported, SMTPHeloError, SMTPDataError,
    SMTPAuthenticationError, SMTPSenderRefused, SMTPRecipientRefused,
    SMTPRecipientsRefused,
)


# These differ only in name
SIMPLE_EXCEPTIONS = (SMTPServerDisconnected, SMTPConnectError,)
SIMPLE_RESPONSE_EXCEPTIONS = (
    SMTPNotSupported, SMTPHeloError, SMTPDataError, SMTPAuthenticationError,)
ERROR_CODES = (
    (503, "Bad command sequence"),
    (530, "Access denied")
)
EMAIL_ADDRESSES = ('a@example.com', 'b@example.com')


@pytest.mark.parametrize('code, message', ERROR_CODES)
def test_raise_smtp_exception(code, message):
    with pytest.raises(SMTPException) as excinfo:
        raise SMTPException(message)

    assert excinfo.value.message == message


@pytest.mark.parametrize('code, message', ERROR_CODES)
def test_raise_smtp_response_exception(code, message):
    with pytest.raises(SMTPResponseException) as excinfo:
        raise SMTPResponseException(code, message)

    assert issubclass(excinfo.type, SMTPException)
    assert excinfo.value.code == code
    assert excinfo.value.message == message


@pytest.mark.parametrize('code, message', ERROR_CODES)
@pytest.mark.parametrize('error_class', SIMPLE_EXCEPTIONS)
def test_simple_exceptions(code, message, error_class):
    with pytest.raises(error_class) as excinfo:
        raise error_class(message)

    assert issubclass(excinfo.type, SMTPException)
    assert excinfo.value.message == message


@pytest.mark.parametrize('code, message', ERROR_CODES)
@pytest.mark.parametrize('error_class', SIMPLE_RESPONSE_EXCEPTIONS)
def test_simple_response_exceptions(code, message, error_class):
    with pytest.raises(error_class) as excinfo:
        raise error_class(code, message)

    assert issubclass(excinfo.type, SMTPResponseException)
    assert excinfo.value.code == code
    assert excinfo.value.message == message


@pytest.mark.parametrize('code, message', ERROR_CODES)
@pytest.mark.parametrize('sender', EMAIL_ADDRESSES)
def test_raise_smtp_sender_refused(code, message, sender):
    with pytest.raises(SMTPSenderRefused) as excinfo:
        raise SMTPSenderRefused(code, message, sender)

    assert issubclass(excinfo.type, SMTPResponseException)
    assert excinfo.value.code == code
    assert excinfo.value.message == message
    assert excinfo.value.sender == sender


@pytest.mark.parametrize('code, message', ERROR_CODES)
@pytest.mark.parametrize('recipient', EMAIL_ADDRESSES)
def test_raise_smtp_recipient_refused(code, message, recipient):
    with pytest.raises(SMTPRecipientRefused) as excinfo:
        raise SMTPRecipientRefused(code, message, recipient)

    assert issubclass(excinfo.type, SMTPResponseException)
    assert excinfo.value.code == code
    assert excinfo.value.message == message
    assert excinfo.value.recipient == recipient

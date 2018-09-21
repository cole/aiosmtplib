from hypothesis import given
from hypothesis.strategies import integers, text

from aiosmtplib.response import SMTPResponse


@given(integers(), text())
def test_response_repr(code, message):
    response = SMTPResponse(code, message)
    assert repr(response) == "({}, {})".format(response.code, response.message)


@given(integers(), text())
def test_response_str(code, message):
    response = SMTPResponse(code, message)
    assert str(response) == "{} {}".format(response.code, response.message)

from hypothesis import given
from hypothesis.strategies import integers, text

from aiosmtplib.response import SMTPResponse


@given(integers(), text())
def test_response_repr(code: int, message: str) -> None:
    response = SMTPResponse(code, message)
    assert (
        repr(response)
        == f"SMTPResponse(code={response.code!r}, message={response.message!r})"
    )
    assert eval(repr(response)) == response


@given(integers(), text())
def test_response_str(code: int, message: str) -> None:
    response = SMTPResponse(code, message)
    assert str(response) == f"{response.code} {response.message}"

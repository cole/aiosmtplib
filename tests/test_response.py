from aiosmtplib.response import SMTPResponse


def test_response_repr():
    response = SMTPResponse(250, 'OK')
    assert repr(response) == '({}, {})'.format(response.code, response.message)


def test_response_str():
    response = SMTPResponse(250, 'OK')
    assert str(response) == '{} {}'.format(response.code, response.message)

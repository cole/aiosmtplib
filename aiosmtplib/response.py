"""
aiosmtplib.response
===================

SMTPResponse class, a simple namedtuple of (code, message).
"""
from typing import NamedTuple


__all__ = ('SMTPResponse',)


BaseResponse = NamedTuple('SMTPResponse', [('code', int), ('message', str)])


class SMTPResponse(BaseResponse):
    """
    A namedtuple with some simple convenience methods.

    Consists of a server response code (e.g. 250) and a server response message
    (e.g. 'OK').
    """
    __slots__ = ()

    def __repr__(self) -> str:
        return '({self.code}, {self.message})'.format(self=self)

    def __str__(self) -> str:
        return '{self.code} {self.message}'.format(self=self)

"""
aiosmtplib.response
===================

SMTPResponse class, a simple namedtuple of (code, message).
"""
import collections

__all__ = ('SMTPResponse',)

ResponseBase = collections.namedtuple('SMTPResponse', ['code', 'message'])


class SMTPResponse(ResponseBase):
    """
    A namedtuple with some simple convenience methods.

    Consists of a server response code (e.g. 250) and a server response message
    (e.g. 'OK').
    """
    __slots__ = ()

    def __repr__(self):
        return '({self.code}, {self.message})'.format(self=self)

    def __str__(self):
        return '{self.code} {self.message}'.format(self=self)

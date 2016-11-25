import collections

from aiosmtplib.errors import SMTPResponseException


ResponseBase = collections.namedtuple('SMTPResponse', ['code', 'message'])


class SMTPResponse(ResponseBase):
    __slots__ = ()

    def __repr__(self):
        return '({self.code}, {self.message})'.format(self=self)

    def __str__(self):
        return '{self.code} {self.message}'.format(self=self)

    def raise_for_status(self):
        if not 200 <= self.code < 400:
            raise SMTPResponseException(self.code, self.message)

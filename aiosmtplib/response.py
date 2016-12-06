import collections

__all__ = ('SMTPResponse',)

ResponseBase = collections.namedtuple('SMTPResponse', ['code', 'message'])


class SMTPResponse(ResponseBase):
    __slots__ = ()

    def __repr__(self):
        return '({self.code}, {self.message})'.format(self=self)

    def __str__(self):
        return '{self.code} {self.message}'.format(self=self)

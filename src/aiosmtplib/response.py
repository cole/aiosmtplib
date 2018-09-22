"""
SMTPResponse class, a simple namedtuple of (code, message).
"""
from typing import NamedTuple


__all__ = ("SMTPResponse",)


BaseResponse = NamedTuple("SMTPResponse", [("code", int), ("message", str)])


class SMTPResponse(BaseResponse):
    """
    NamedTuple of server response code and server response message.

    ``code`` and ``message`` can be accessed via attributes or indexes:

        >>> response = SMTPResponse(200, "OK")
        >>> response.message
        'OK'
        >>> response[0]
        200
        >>> response.code
        200

    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "({self.code}, {self.message})".format(self=self)

    def __str__(self) -> str:
        return "{self.code} {self.message}".format(self=self)

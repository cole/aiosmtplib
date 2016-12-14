"""
aiomsmtplib.typing
==================

Type definitions/aliases.
"""
import enum
import ssl
from typing import Callable, Dict, Optional, Tuple, Union

from aiosmtplib.response import SMTPResponse

__all__ = (
    'AuthReturnType', 'AuthFunctionType', 'Default', 'OptionalDefaultNumber',
    'OptionalDefaultStr', 'OptionalDefaultSSLContext', 'OptionalNumber',
    '_default',
)


class Default(enum.Enum):
    """
    Used for type hinting compatible kwarg defaults.
    """
    token = 0


_default = Default.token

# Type aliases
AuthReturnType = Tuple[str, Optional[Callable[[int, str], str]]]
AuthFunctionType = Callable[[str, str], AuthReturnType]
OptionalDefaultNumber = Optional[Union[float, int, Default]]
OptionalDefaultStr = Optional[Union[str, Default]]
OptionalDefaultSSLContext = Optional[Union[ssl.SSLContext, Default]]
OptionalNumber = Optional[Union[int, float]]
SendmailResponse = Tuple[Dict[str, SMTPResponse], str]

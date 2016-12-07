"""
aiosmtplib: asyncio SMTP client
"""

__title__ = 'aiosmtplib'
__version__ = '0.1.7'
__author__ = 'Cole Maclean'
__license__ = 'MIT'
__copyright__ = 'Copyright 2016 Cole Maclean'


from .errors import *  # NOQA
from .response import *  # NOQA
from .smtp import *  # NOQA
from .status import *  # NOQA

__all__ = (
    errors.__all__ + response.__all__ + smtp.__all__ + status.__all__  # NOQA
)

"""
aiosmtplib
==========

An asyncio SMTP client.

Originally based on smtplib from the Python 3 standard library by:
The Dragon De Monsyne <dragondm@integral.org>

Author: Cole Maclean <hi@cole.io>
"""
from .api import *  # NOQA
from .errors import *  # NOQA
from .response import *  # NOQA
from .smtp import *  # NOQA
from .status import *  # NOQA


__title__ = "aiosmtplib"
__version__ = "1.1a0"
__author__ = "Cole Maclean"
__license__ = "MIT"
__copyright__ = "Copyright 2019 Cole Maclean"
__all__ = (
    api.__all__  # NOQA
    + errors.__all__  # NOQA
    + response.__all__  # NOQA
    + smtp.__all__  # NOQA
    + status.__all__  # NOQA
)

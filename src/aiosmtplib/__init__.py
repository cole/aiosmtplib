"""
aiosmtplib
==========

An asyncio SMTP client.

Roughly based (with API differences) on smtplib from the Python 3 standard
library by: The Dragon De Monsyne <dragondm@integral.org>

Author: Cole Maclean <hi@cole.io>
"""
from .errors import *  # NOQA
from .response import *  # NOQA
from .smtp import *  # NOQA
from .status import *  # NOQA


__title__ = "aiosmtplib"
__version__ = "1.0.4"
__author__ = "Cole Maclean"
__license__ = "MIT"
__copyright__ = "Copyright 2019 Cole Maclean"
__all__ = errors.__all__ + response.__all__ + smtp.__all__ + status.__all__  # NOQA

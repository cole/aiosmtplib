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
from .smtp import SMTP
from .status import *  # NOQA


__title__ = 'aiosmtplib'
__version__ = '1.0.1'
__author__ = 'Cole Maclean'
__license__ = 'MIT'
__copyright__ = 'Copyright 2017 Cole Maclean'
__all__ = (
    errors.__all__ + response.__all__ + smtp.__all__ + status.__all__  # NOQA
)


if __name__ == '__main__':

    def main() -> None:
        hostname = input('SMTP server hostname [localhost]: ') or 'localhost'
        port = int(input('SMTP server port [25]: ') or '25')
        sender = input('From: ')
        recipients = input('To: ').split(',')

        print('Enter message, end with ^D:')
        lines = []

        while True:
            try:
                lines.append(input())
            except EOFError:
                break

        message = '\n'.join(lines)
        message_len = len(message.encode('utf-8'))

        print('Message length (bytes): {}'.format(message_len))

        smtp_client = SMTP(hostname=hostname, port=port)
        sendmail_errors, sendmail_response = smtp_client.sendmail_sync(
            sender, recipients, message)

        print('Server response: {}'.format(sendmail_response))

    main()

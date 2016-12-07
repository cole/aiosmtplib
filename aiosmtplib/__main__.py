"""
aiosmtplib
==========

When executed directly, send a single message from the command line.
"""

import asyncio
import sys

from .smtp import SMTP


def prompt(prompt):
    sys.stdout.write(prompt + ': ')
    sys.stdout.flush()
    return sys.stdin.readline().strip()


async def send(hostname, port, sender, recipients, message, loop=None):
    smtp = SMTP(hostname=hostname, port=port, loop=loop)
    async with smtp:
        await smtp.sendmail(sender, recipients, message)


hostname = prompt('SMTP server hostname [localhost]') or 'localhost'
port = prompt('SMTP server port [25]') or 25
sender = prompt('From')
recipients = prompt('To').split(',')
print('Enter message, end with ^D:')
message = []

while True:
    line = sys.stdin.readline()
    if line:
        message.append(line)
    else:
        break

full_message = '\n'.join(message)
print('Message length is {}'.format(len(full_message)))

loop = asyncio.get_event_loop()
loop.run_until_complete(
    send(hostname, port, sender, recipients, full_message, loop=loop))

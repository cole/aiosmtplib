"""
aiosmtplib
==========

When executed directly, send a single message from the command line.
"""
from .smtp import SMTP


def main():
    hostname = input('SMTP server hostname [localhost]: ') or 'localhost'
    port = int(input('SMTP server port [25]: ') or 25)
    sender = input('From: ')
    recipients = input('To: ').split(',')
    print('Enter message, end with ^D:')
    message = []

    while True:
        try:
            line = input()
        except EOFError:
            break
        else:
            message.append(line)

    full_message = '\n'.join(message)
    full_message = full_message.encode('ascii')

    print('Message length (bytes): {}'.format(len(full_message)))

    smtp = SMTP(hostname=hostname, port=port)
    recipient_errors, response = smtp.sendmail_sync(
        sender, recipients, full_message)

    print('Server response: {}'.format(response))


main()

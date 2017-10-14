from aiosmtplib.connection import SMTP_PORT
from aiosmtplib.errors import SMTPException
from aiosmtplib.smtp import SMTP


def main() -> None:
    hostname = input('SMTP server hostname [localhost]: ')  # nosec
    port = input('SMTP server port [{}]: '.format(SMTP_PORT))  # nosec
    sender = input('From: ')  # nosec
    recipients = input('To: ').split(',')  # nosec

    print('Enter message, end with ^D:')
    lines = []

    while True:
        try:
            lines.append(input())  # nosec
        except EOFError:
            break

    message = '\n'.join(lines)
    message_len = len(message.encode('utf-8'))

    print('Message length (bytes): {}'.format(message_len))

    smtp_client = SMTP(
        hostname=hostname or 'localhost',
        port=int(port) if port else SMTP_PORT)
    try:
        sendmail_errors, sendmail_response = smtp_client.sendmail_sync(
            sender, recipients, message)
    except SMTPException as exc:
        print('{}: {}'.format(exc.__class__.__name__, exc))
    else:
        print('Server response: {}'.format(sendmail_response))


if __name__ == '__main__':
    main()

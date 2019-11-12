from aiosmtplib.connection import SMTP_PORT
from aiosmtplib.smtp import SMTP


raw_hostname = input("SMTP server hostname [localhost]: ")  # nosec
raw_port = input("SMTP server port [{}]: ".format(SMTP_PORT))  # nosec
raw_sender = input("From: ")  # nosec
raw_recipients = input("To: ")  # nosec

hostname = raw_hostname or "localhost"
port = int(raw_port) if raw_port else SMTP_PORT
recipients = raw_recipients.split(",")
lines = []

print("Enter message, end with ^D:")
while True:
    try:
        lines.append(input())  # nosec
    except EOFError:
        break

message = "\n".join(lines)

print("Message length (bytes): {}".format(len(message.encode("utf-8"))))

smtp_client = SMTP(hostname=hostname or "localhost", port=port)
sendmail_errors, sendmail_response = smtp_client.sendmail_sync(
    raw_sender, recipients, message
)

print("Server response: {}".format(sendmail_response))

import email.mime.multipart
import email.mime.text


def test_sendmail_sync(smtpd_client):
    test_address = 'test@example.com'
    mail_text = """
    Hello world!

    -a tester
    """
    errors, message = smtpd_client.sendmail_sync(
        test_address, [test_address], mail_text)

    assert not errors
    assert isinstance(errors, dict)
    assert message != ''


def test_sendmail_sync_when_connected(smtpd_client):
    test_address = 'test@example.com'
    mail_text = "hello world"

    smtpd_client.loop.run_until_complete(smtpd_client.connect())

    errors, message = smtpd_client.sendmail_sync(
        test_address, [test_address], mail_text)

    assert not errors
    assert isinstance(errors, dict)
    assert message != ''


def test_send_message_sync(smtpd_client):
    message = email.mime.multipart.MIMEMultipart()
    message['To'] = 'test@example.com'
    message['From'] = 'test@example.com'
    message['Subject'] = 'tëst message'
    body = email.mime.text.MIMEText("""
    Hello world. UTF8 OK? 15£ ümläüts'r'us
    """)
    message.attach(body)

    errors, message = smtpd_client.send_message_sync(message)

    assert not errors
    assert isinstance(errors, dict)
    assert message != ''

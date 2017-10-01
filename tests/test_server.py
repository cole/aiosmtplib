"""
Check that our test server behaves properly.
"""
import smtplib
import ssl

from aiosmtplib import SMTPStatus


def test_mock_server_starttls_with_smtplib(preset_server):
    smtp = smtplib.SMTP()
    smtp._host = preset_server.hostname  # Hack around smtplib SNI bug
    smtp.connect(host=preset_server.hostname, port=preset_server.port)
    preset_server.responses.append(b'\n'.join([
        b'250-localhost, hello',
        b'250-SIZE 100000',
        b'250 STARTTLS',
    ]))

    code, message = smtp.ehlo()
    assert code == SMTPStatus.completed

    preset_server.responses.append(b'220 ready for TLS')
    code, message = smtp.starttls()
    assert code == SMTPStatus.ready

    # make sure our connection was actually upgraded
    assert isinstance(smtp.sock, ssl.SSLSocket)

    preset_server.responses.append(b'250 all good')
    code, message = smtp.ehlo()
    assert code == SMTPStatus.completed

import asyncio
import asyncio.test_utils
import functools
import unittest
import logging
import email.mime.text
import email.mime.multipart

from .smtp import SMTP
from .errors import (
    SMTPServerDisconnected, SMTPResponseException, SMTPConnectError,
    SMTPHeloError, SMTPDataError, SMTPRecipientsRefused,
)


# NOTE: this sends real emails! change the address before running.
TEST_ADDRESS = 'root@localhost'
TEST_HOSTNAME = 'localhost'
TEST_PORT = 1025


def async_test(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        coroutine = asyncio.coroutine(f)
        future = coroutine(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.set_debug(False)
        loop.run_until_complete(future)
    return wrapper


class SMTPTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.loop = asyncio.get_event_loop()
        cls.smtp = SMTP(hostname=TEST_HOSTNAME, port=TEST_PORT, loop=cls.loop)

    def setUp(self):
        self.smtp.last_helo_status = (None, None)

    @async_test
    def test_helo_ok(self):
        code, message = yield from self.smtp.helo()
        self.assertTrue(200 <= code <= 299)

    @async_test
    def test_ehlo_ok(self):
        code, message = yield from self.smtp.ehlo()
        self.assertTrue(200 <= code <= 299)

    @async_test
    def test_helo_if_needed_when_needed(self):
        yield from self.smtp.ehlo_or_helo_if_needed()
        self.assertTrue(200 <= self.smtp.last_helo_status[0] <= 299)

    @async_test
    def test_helo_if_needed_when_not_needed(self):
        yield from self.smtp.helo()
        self.assertTrue(200 <= self.smtp.last_helo_status[0] <= 299)
        self.smtp.last_helo_status = ('Test', 'Test')
        yield from self.smtp.ehlo_or_helo_if_needed()
        self.assertEqual(self.smtp.last_helo_status, ('Test', 'Test'))

    @async_test
    def test_rset_ok(self):
        code, message = yield from self.smtp.rset()
        self.assertTrue(200 <= code <= 299)

    @async_test
    def test_noop_ok(self):
        code, message = yield from self.smtp.noop()
        self.assertTrue(200 <= code <= 299)

    @async_test
    def test_vrfy_ok(self):
        code, message = yield from self.smtp.vrfy(TEST_ADDRESS)
        self.assertTrue(200 <= code <= 299)

    def test_vrfy_failure(self):
        bad_address = 'test@---'
        with self.assertRaises(SMTPResponseException):
            yield from self.smtp.vrfy(bad_address)

    # These commands aren't supported on my test system
    # @async_test
    # def test_expn_ok(self):
    #     code, message = yield from self.smtp.expn(TEST_ADDRESS)
    #     self.assertTrue(200 <= code <= 299)
    #
    # @async_test
    # def test_help_ok(self):
    #     message = yield from self.smtp.help()
    #     self.assertNotEqual(message, "")

    @async_test
    def test_supports_method(self):
        code, message = yield from self.smtp.ehlo()
        self.assertTrue(self.smtp.supports('ENHANCEDSTATUSCODES'))
        self.assertTrue(self.smtp.supports('VRFY'))
        self.assertFalse(self.smtp.supports('BOGUSEXT'))

    @async_test
    def test_sendmail_simple(self):
        mail_text = """
        Hello world!

        -a tester
        """
        errors = yield from self.smtp.sendmail(TEST_ADDRESS,
                                               [TEST_ADDRESS], mail_text)
        self.assertFalse(errors)

    @async_test
    def test_sendmail_bogus(self):
        with self.assertRaises(SMTPRecipientsRefused):
            yield from self.smtp.sendmail(TEST_ADDRESS,
                                          ['noonehere@localhost'],
                                          'blah blah blah')

    @async_test
    def test_send_message(self):
        message = email.mime.multipart.MIMEMultipart()
        message['To'] = TEST_ADDRESS
        message['From'] = TEST_ADDRESS
        message['Subject'] = 'tëst message'
        body = email.mime.text.MIMEText("""
        Hello world. UTF8 OK? 15£ ümläüts'r'us
        """)
        message.attach(body)
        errors = yield from self.smtp.send_message(message)
        self.assertFalse(errors)

    @async_test
    def test_quit_reconnect_ok(self):
        code, message = yield from self.smtp.quit()
        self.assertTrue(200 <= code <= 299)
        # Next command should fail
        with self.assertRaises(SMTPServerDisconnected):
            code, message = yield from self.smtp.noop()
        yield from self.smtp.reconnect()
        # after reconnect, it should work again
        code, message = yield from self.smtp.noop()
        self.assertTrue(200 <= code <= 299)

    @classmethod
    def tearDownClass(cls):
        future = asyncio.async(cls.smtp.close())
        cls.loop.run_until_complete(future)
        cls.stmp = None
        cls.loop = None

if __name__ == '__main__':
    unittest.main()

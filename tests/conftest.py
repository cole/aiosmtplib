"""
Pytest fixtures and config.
"""
import asyncio
import email.mime.multipart
import email.mime.text
import ssl
import sys
from email.errors import HeaderParseError
from email.message import Message
from pathlib import Path

import pytest
from aiosmtpd.handlers import Message as MessageHandler
from aiosmtpd.smtp import MISSING
from aiosmtpd.smtp import SMTP as SMTPD

from aiosmtplib import SMTP


PY36_OR_LATER = sys.version_info[:2] >= (3, 6)
PY37_OR_LATER = sys.version_info[:2] >= (3, 7)
try:
    import uvloop
except ImportError:
    HAS_UVLOOP = False
else:
    HAS_UVLOOP = True
BASE_CERT_PATH = Path("tests/certs/")


def pytest_addoption(parser):
    parser.addoption(
        "--event-loop", action="store", default="asyncio", choices=["asyncio", "uvloop"]
    )


class RecordingHandler(MessageHandler):
    HELO_response_message = None
    EHLO_response_message = None
    NOOP_response_message = None
    QUIT_response_message = None
    VRFY_response_message = None
    MAIL_response_message = None
    RCPT_response_message = None
    DATA_response_message = None
    RSET_response_message = None
    EXPN_response_message = None
    HELP_response_message = None

    def __init__(self, messages_list, commands_list, responses_list):
        self.messages = messages_list
        self.commands = commands_list
        self.responses = responses_list
        super().__init__(message_class=Message)

    def record_command(self, command, *args):
        self.commands.append((command, *args))

    def record_server_response(self, status):
        self.responses.append(status)

    def handle_message(self, message):
        self.messages.append(message)


class TestSMTPD(SMTPD):
    def _getaddr(self, arg):
        """
        Don't raise an exception on unparsable email address
        """
        try:
            return super()._getaddr(arg)
        except HeaderParseError:
            return None, ""

    async def _call_handler_hook(self, command, *args):
        self.event_handler.record_command(command, *args)

        hook_response = await super()._call_handler_hook(command, *args)
        response_message = getattr(
            self.event_handler, command + "_response_message", None
        )

        return response_message or hook_response

    async def push(self, status):
        result = await super().push(status)
        self.event_handler.record_server_response(status)

        return result

    async def smtp_EXPN(self, arg):
        """
        Pass EXPN to handler hook.
        """
        status = await self._call_handler_hook("EXPN")
        await self.push("502 EXPN not implemented" if status is MISSING else status)

    async def smtp_HELP(self, arg):
        """
        Override help to pass to handler hook.
        """
        status = await self._call_handler_hook("HELP")
        if status is MISSING:
            await super().smtp_HELP(arg)
        else:
            await self.push(status)

    async def smtp_STARTTLS(self, arg):
        """
        Override for uvloop compatibility.
        """
        if arg:
            await self.push("501 Syntax: STARTTLS")
            return
        if not self.tls_context:
            await self.push("454 TLS not available")
            return
        await self.push("220 Ready to start TLS")
        # Create SSL layer.
        self._tls_protocol = asyncio.sslproto.SSLProtocol(
            self.loop, self, self.tls_context, None, server_side=True
        )
        self._original_transport = self.transport
        if hasattr(self._original_transport, "set_protocol"):
            self._original_transport.set_protocol(self._tls_protocol)
        else:
            self._original_transport._protocol = self._tls_protocol

        self.transport = self._tls_protocol._app_transport
        self._tls_protocol.connection_made(self._original_transport)


@pytest.fixture(scope="function")
def event_loop(request):
    loop_type = request.config.getoption("--event-loop")
    if loop_type == "uvloop" and not HAS_UVLOOP:
        raise RuntimeError("uvloop not installed.")

    if loop_type == "asyncio":
        loop = asyncio.new_event_loop()
    elif loop_type == "uvloop":
        loop = uvloop.new_event_loop()
    else:
        raise ValueError("Unknown event loop type: {}".format(loop_type))

    yield loop

    # Cancel any pending tasks
    if PY37_OR_LATER:
        cleanup_tasks = asyncio.all_tasks(loop=loop)
    else:
        cleanup_tasks = asyncio.Task.all_tasks(loop=loop)

    if cleanup_tasks:
        for task in cleanup_tasks:
            task.cancel()
        try:
            loop.run_until_complete(asyncio.wait(cleanup_tasks, loop=loop, timeout=1.0))
        except RuntimeError:
            # Event loop was probably already stopping.
            pass

    if PY36_OR_LATER:
        loop.run_until_complete(loop.shutdown_asyncgens())

    loop.call_soon(loop.stop)
    loop.run_forever()

    loop.close()


@pytest.fixture(scope="session")
def hostname(request):
    return "localhost"


@pytest.fixture(scope="function")
def port(request, unused_tcp_port):
    """Alias for ununsed_tcp_port."""
    return unused_tcp_port


@pytest.fixture(scope="session")
def message(request):
    message = email.mime.multipart.MIMEMultipart()
    message["To"] = "recipient@example.com"
    message["From"] = "sender@example.com"
    message["Subject"] = "A message"
    message.attach(email.mime.text.MIMEText("Hello World"))

    return message


@pytest.fixture(scope="function")
def recieved_messages(request):
    return []


@pytest.fixture(scope="function")
def recieved_commands(request):
    return []


@pytest.fixture(scope="function")
def smtpd_responses(request):
    return []


@pytest.fixture(scope="function")
def smtpd_handler(request, recieved_messages, recieved_commands, smtpd_responses):
    return RecordingHandler(recieved_messages, recieved_commands, smtpd_responses)


@pytest.fixture(scope="session")
def smtpd_class(request):
    return TestSMTPD


@pytest.fixture(scope="session")
def valid_cert_path(request):
    return str(BASE_CERT_PATH.joinpath("selfsigned.crt"))


@pytest.fixture(scope="session")
def valid_key_path(request):
    return str(BASE_CERT_PATH.joinpath("selfsigned.key"))


@pytest.fixture(scope="session")
def invalid_cert_path(request):
    return str(BASE_CERT_PATH.joinpath("invalid.crt"))


@pytest.fixture(scope="session")
def invalid_key_path(request):
    return str(BASE_CERT_PATH.joinpath("invalid.key"))


@pytest.fixture(scope="session")
def client_tls_context(request, valid_cert_path, valid_key_path):
    tls_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    tls_context.check_hostname = False
    tls_context.verify_mode = ssl.CERT_NONE

    return tls_context


@pytest.fixture(scope="session")
def server_tls_context(request, valid_cert_path, valid_key_path):
    tls_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    tls_context.load_cert_chain(valid_cert_path, keyfile=valid_key_path)

    return tls_context


@pytest.fixture(scope="function")
def smtpd_server(
    request, event_loop, hostname, port, smtpd_class, smtpd_handler, server_tls_context
):
    def factory():
        return smtpd_class(
            smtpd_handler,
            hostname=hostname,
            enable_SMTPUTF8=False,
            tls_context=server_tls_context,
        )

    server = event_loop.run_until_complete(
        event_loop.create_server(factory, host=hostname, port=port)
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def smtp_client(request, event_loop, hostname, port):
    client = SMTP(hostname=hostname, port=port, loop=event_loop, timeout=1.0)

    return client

"""
Pytest fixtures and config.
"""
import asyncio
import email.mime.multipart
import email.mime.text
import socket
import ssl
from pathlib import Path

import pytest

from aiosmtplib import SMTP
from aiosmtplib.sync import shutdown_loop

from .mocks import EchoServerProtocol
from .smtpd import RecordingHandler, TestSMTPD


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


@pytest.fixture(scope="session")
def event_loop_policy(request):
    loop_type = request.config.getoption("--event-loop")
    if loop_type == "uvloop":
        if not HAS_UVLOOP:
            raise RuntimeError("uvloop not installed.")
        old_policy = asyncio.get_event_loop_policy()
        policy = uvloop.EventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
        request.addfinalizer(lambda: asyncio.set_event_loop_policy(old_policy))

    return asyncio.get_event_loop_policy()


@pytest.fixture(scope="function")
def event_loop(request, event_loop_policy):
    old_loop = event_loop_policy.get_event_loop()
    loop = event_loop_policy.new_event_loop()
    event_loop_policy.set_event_loop(loop)

    def cleanup():
        shutdown_loop(loop)
        event_loop_policy.set_event_loop(old_loop)

    request.addfinalizer(cleanup)

    return loop


@pytest.fixture(scope="session")
def hostname(request):
    return "localhost"


@pytest.fixture(scope="function")
def port(request, unused_tcp_port):
    """Alias for ununsed_tcp_port."""
    return unused_tcp_port


@pytest.fixture(scope="function")
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
        event_loop.create_server(
            factory, host=hostname, port=port, family=socket.AF_INET
        )
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="session")
def smtpd_response_handler(request):
    def smtpd_response(response_text, write_eof=False, close_after=False):
        async def response_handler(smtpd, *args, **kwargs):
            if args and args[0]:
                smtpd.session.host_name = args[0]
            if response_text is not None:
                await smtpd.push(response_text)
            if write_eof:
                smtpd.transport.write_eof()
            if close_after:
                smtpd.transport.close()

        return response_handler

    return smtpd_response


@pytest.fixture(scope="function")
def smtp_client(request, event_loop, hostname, port):
    client = SMTP(hostname=hostname, port=port, loop=event_loop, timeout=1.0)

    return client


@pytest.fixture(scope="function")
def echo_server(request, hostname, port, event_loop):
    server = event_loop.run_until_complete(
        event_loop.create_server(
            EchoServerProtocol, host=hostname, port=port, family=socket.AF_INET
        )
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

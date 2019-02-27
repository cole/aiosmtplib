"""
Pytest fixtures and config.
"""
import asyncio
import email.mime.multipart
import email.mime.text
import ssl
import sys
from pathlib import Path

import pytest

from aiosmtplib import SMTP

from .smtpd import RecordingHandler, TestSMTPD


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

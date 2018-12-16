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
from testserver import SMTPPresetServer, RecordingHandler, TestSMTPD


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
            loop.run_until_complete(
                asyncio.wait(cleanup_tasks, loop=loop, timeout=0.01)
            )
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
def smtpd_commands(request):
    return []


@pytest.fixture(scope="function")
def smtpd_responses(request):
    return []


@pytest.fixture(scope="function")
def smtpd_handler(request, recieved_messages, smtpd_commands, smtpd_responses):
    return RecordingHandler(recieved_messages, smtpd_commands, smtpd_responses)


@pytest.fixture(scope="session")
def aiosmtpd_class(request):
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
def server_tls_context(request, valid_cert_path, valid_key_path):
    tls_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    tls_context.load_cert_chain(valid_cert_path, keyfile=valid_key_path)

    return tls_context


@pytest.fixture(scope="function")
def aiosmtpd_factory(request, hostname, port, aiosmtpd_class, smtpd_handler):
    def factory():
        return aiosmtpd_class(smtpd_handler, hostname=hostname, enable_SMTPUTF8=False)

    return factory


@pytest.fixture(scope="function")
def starttls_aiosmtpd_factory(
    request, hostname, port, aiosmtpd_class, smtpd_handler, server_tls_context
):
    def factory():
        return aiosmtpd_class(
            smtpd_handler,
            hostname=hostname,
            enable_SMTPUTF8=False,
            tls_context=server_tls_context,
        )

    return factory


@pytest.fixture(scope="function")
def smtpd_server(request, event_loop, hostname, port, aiosmtpd_factory):
    server = event_loop.run_until_complete(
        event_loop.create_server(aiosmtpd_factory, host=hostname, port=port)
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def starttls_smtpd_server(
    request, event_loop, hostname, port, starttls_aiosmtpd_factory
):
    server = event_loop.run_until_complete(
        event_loop.create_server(starttls_aiosmtpd_factory, host=hostname, port=port)
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def tls_smtpd_server(
    request, event_loop, hostname, port, aiosmtpd_factory, server_tls_context
):
    server = event_loop.run_until_complete(
        event_loop.create_server(
            aiosmtpd_factory, host=hostname, port=port, ssl=server_tls_context
        )
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def preset_server(request, event_loop, unused_tcp_port):
    server = SMTPPresetServer("localhost", unused_tcp_port, loop=event_loop)

    event_loop.run_until_complete(server.start())

    def close_server():
        event_loop.run_until_complete(server.stop())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def smtp_client(request, event_loop, hostname, port):
    client = SMTP(hostname=hostname, port=port, loop=event_loop, timeout=0.1)

    return client


@pytest.fixture(scope="function")
def tls_smtp_client(request, event_loop, hostname, port):
    tls_client = SMTP(
        hostname=hostname,
        port=port,
        loop=event_loop,
        use_tls=True,
        validate_certs=False,
    )

    return tls_client


@pytest.fixture(scope="function")
def preset_client(request, preset_server, event_loop, hostname, port):
    client = SMTP(hostname=hostname, port=port, loop=event_loop, timeout=1)
    client.server = preset_server

    return client

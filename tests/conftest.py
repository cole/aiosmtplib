"""
Pytest fixtures and config.
"""
import asyncio
import email.header
import email.message
import email.mime.multipart
import email.mime.text
import socket
import ssl
import sys
import traceback
from pathlib import Path

import hypothesis
import pytest

from aiosmtplib import SMTP, SMTPStatus
from aiosmtplib.sync import shutdown_loop

from .smtpd import RecordingHandler, SMTPDController, TestSMTPD


try:
    import uvloop
except ImportError:
    HAS_UVLOOP = False
else:
    HAS_UVLOOP = True
BASE_CERT_PATH = Path("tests/certs/")
IS_PYPY = hasattr(sys, "pypy_version_info")

# pypy can take a while to generate data, so don't fail the test due to health checks.
if IS_PYPY:
    base_settings = hypothesis.settings(
        suppress_health_check=(hypothesis.HealthCheck.too_slow,)
    )
else:
    base_settings = hypothesis.settings()
hypothesis.settings.register_profile("dev", parent=base_settings, max_examples=10)
hypothesis.settings.register_profile("ci", parent=base_settings, max_examples=100)


class AsyncPytestWarning(pytest.PytestWarning):
    pass


def pytest_addoption(parser):
    parser.addoption(
        "--event-loop",
        action="store",
        default="asyncio",
        choices=["asyncio", "uvloop"],
        help="event loop to run tests on",
    )
    parser.addoption(
        "--bind-addr",
        action="store",
        default="127.0.0.1",
        help="server address to bind on, e.g 127.0.0.1",
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
    verbosity = request.config.getoption("verbose", default=0)
    old_loop = event_loop_policy.get_event_loop()
    loop = event_loop_policy.new_event_loop()
    event_loop_policy.set_event_loop(loop)

    def handle_async_exception(loop, context):
        message = "{}: {}".format(context["message"], repr(context["exception"]))
        if verbosity > 1:
            message += "\n"
            message += "Future: {}".format(repr(context["future"]))
            message += "\nTraceback:\n"
            message += "".join(traceback.format_list(context["source_traceback"]))

        request.node.warn(AsyncPytestWarning(message))

    loop.set_exception_handler(handle_async_exception)

    def cleanup():
        shutdown_loop(loop)
        event_loop_policy.set_event_loop(old_loop)

    request.addfinalizer(cleanup)

    return loop


@pytest.fixture(scope="session")
def hostname(request):
    return "localhost"


@pytest.fixture(scope="session")
def bind_address(request):
    """Server side address for socket binding"""
    return request.config.getoption("--bind-addr")


@pytest.fixture(
    scope="function",
    params=(
        str,
        bytes,
        pytest.param(
            lambda path: path,
            marks=pytest.mark.xfail(
                sys.version_info < (3, 7),
                reason="os.PathLike support introduced in 3.7.",
            ),
        ),
    ),
    ids=("str", "bytes", "pathlike"),
)
def socket_path(request, tmp_path):
    if sys.platform.startswith("darwin"):
        # Work around OSError: AF_UNIX path too long
        tmp_dir = Path("/tmp")  # nosec
    else:
        tmp_dir = tmp_path

    index = 0
    socket_path = tmp_dir / "aiosmtplib-test{}".format(index)
    while socket_path.exists():
        index += 1
        socket_path = tmp_dir / "aiosmtplib-test{}".format(index)

    return request.param(socket_path)


@pytest.fixture(scope="function")
def compat32_message(request):
    message = email.message.Message()
    message["To"] = email.header.Header("recipient@example.com")
    message["From"] = email.header.Header("sender@example.com")
    message["Subject"] = "A message"
    message.set_payload("Hello World")

    return message


@pytest.fixture(scope="function")
def mime_message(request):
    message = email.mime.multipart.MIMEMultipart()
    message["To"] = "recipient@example.com"
    message["From"] = "sender@example.com"
    message["Subject"] = "A message"
    message.attach(email.mime.text.MIMEText("Hello World"))

    return message


@pytest.fixture(scope="function", params=["mime_multipart", "compat32"])
def message(request, compat32_message, mime_message):
    if request.param == "compat32":
        return compat32_message
    else:
        return mime_message


@pytest.fixture(scope="session")
def recipient_str(request):
    return "recipient@example.com"


@pytest.fixture(scope="session")
def sender_str(request):
    return "sender@example.com"


@pytest.fixture(scope="session")
def message_str(request, recipient_str, sender_str):
    return (
        "Content-Type: multipart/mixed; "
        'boundary="===============6842273139637972052=="\n'
        "MIME-Version: 1.0\n"
        "To: recipient@example.com\n"
        "From: sender@example.com\n"
        "Subject: A message\n\n"
        "--===============6842273139637972052==\n"
        'Content-Type: text/plain; charset="us-ascii"\n'
        "MIME-Version: 1.0\n"
        "Content-Transfer-Encoding: 7bit\n\n"
        "Hello World\n"
        "--===============6842273139637972052==--\n"
    )


@pytest.fixture(scope="function")
def received_messages(request):
    return []


@pytest.fixture(scope="function")
def received_commands(request):
    return []


@pytest.fixture(scope="function")
def smtpd_responses(request):
    return []


@pytest.fixture(scope="function")
def smtpd_handler(request, received_messages, received_commands, smtpd_responses):
    return RecordingHandler(received_messages, received_commands, smtpd_responses)


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
    request,
    event_loop,
    bind_address,
    hostname,
    smtpd_class,
    smtpd_handler,
    server_tls_context,
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
            factory, host=bind_address, port=0, family=socket.AF_INET
        )
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def smtpd_server_port(request, smtpd_server):
    return smtpd_server.sockets[0].getsockname()[1]


@pytest.fixture(scope="function")
def smtpd_server_smtputf8(
    request,
    event_loop,
    bind_address,
    hostname,
    smtpd_class,
    smtpd_handler,
    server_tls_context,
):
    def factory():
        return smtpd_class(
            smtpd_handler,
            hostname=hostname,
            enable_SMTPUTF8=True,
            tls_context=server_tls_context,
        )

    server = event_loop.run_until_complete(
        event_loop.create_server(
            factory, host=bind_address, port=0, family=socket.AF_INET
        )
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def smtpd_server_smtputf8_port(request, smtpd_server_smtputf8):
    return smtpd_server_smtputf8.sockets[0].getsockname()[1]


@pytest.fixture(scope="function")
def smtpd_server_socket_path(
    request, socket_path, event_loop, smtpd_class, smtpd_handler, server_tls_context
):
    def factory():
        return smtpd_class(
            smtpd_handler,
            hostname=hostname,
            enable_SMTPUTF8=False,
            tls_context=server_tls_context,
        )

    server = event_loop.run_until_complete(
        event_loop.create_unix_server(factory, path=socket_path)
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="session")
def smtpd_response_handler_factory(request):
    def smtpd_response(
        response_text, second_response_text=None, write_eof=False, close_after=False
    ):
        async def response_handler(smtpd, *args, **kwargs):
            if args and args[0]:
                smtpd.session.host_name = args[0]
            if response_text is not None:
                await smtpd.push(response_text)
            if write_eof:
                smtpd.transport.write_eof()
            if second_response_text is not None:
                await smtpd.push(second_response_text)
            if close_after:
                smtpd.transport.close()

        return response_handler

    return smtpd_response


@pytest.fixture(scope="function")
def smtp_client(request, event_loop, hostname, smtpd_server_port):
    client = SMTP(hostname=hostname, port=smtpd_server_port, timeout=1.0)

    return client


@pytest.fixture(scope="function")
def smtp_client_smtputf8(request, event_loop, hostname, smtpd_server_smtputf8_port):
    client = SMTP(hostname=hostname, port=smtpd_server_smtputf8_port, timeout=1.0)

    return client


class EchoServerProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self.transport.write(data)


@pytest.fixture(scope="function")
def echo_server(request, bind_address, event_loop):
    server = event_loop.run_until_complete(
        event_loop.create_server(
            EchoServerProtocol, host=bind_address, port=0, family=socket.AF_INET
        )
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def echo_server_port(request, echo_server):
    return echo_server.sockets[0].getsockname()[1]


@pytest.fixture(
    params=[
        SMTPStatus.mailbox_unavailable,
        SMTPStatus.unrecognized_command,
        SMTPStatus.bad_command_sequence,
        SMTPStatus.syntax_error,
    ],
    ids=[
        SMTPStatus.mailbox_unavailable.name,
        SMTPStatus.unrecognized_command.name,
        SMTPStatus.bad_command_sequence.name,
        SMTPStatus.syntax_error.name,
    ],
)
def error_code(request):
    return request.param


@pytest.fixture(scope="function")
def tls_smtpd_server(
    request, event_loop, bind_address, smtpd_class, smtpd_handler, server_tls_context
):
    def factory():
        return smtpd_class(
            smtpd_handler,
            hostname=bind_address,
            enable_SMTPUTF8=False,
            tls_context=server_tls_context,
        )

    server = event_loop.run_until_complete(
        event_loop.create_server(
            factory,
            host=bind_address,
            port=0,
            ssl=server_tls_context,
            family=socket.AF_INET,
        )
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def tls_smtpd_server_port(request, tls_smtpd_server):
    return tls_smtpd_server.sockets[0].getsockname()[1]


@pytest.fixture(scope="function")
def tls_smtp_client(request, event_loop, hostname, tls_smtpd_server_port):
    tls_client = SMTP(
        hostname=hostname,
        port=tls_smtpd_server_port,
        use_tls=True,
        validate_certs=False,
    )

    return tls_client


@pytest.fixture(scope="function")
def threaded_smtpd_server(request, bind_address, smtpd_handler):
    controller = SMTPDController(smtpd_handler, hostname=bind_address, port=0)
    controller.start()
    request.addfinalizer(controller.stop)

    return controller.server


@pytest.fixture(scope="function")
def threaded_smtpd_server_port(request, threaded_smtpd_server):
    return threaded_smtpd_server.sockets[0].getsockname()[1]


@pytest.fixture(scope="function")
def smtp_client_threaded(request, hostname, threaded_smtpd_server_port):
    client = SMTP(hostname=hostname, port=threaded_smtpd_server_port, timeout=1.0)

    return client

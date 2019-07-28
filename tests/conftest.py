"""
Pytest fixtures and config.
"""
import asyncio
import email.mime.multipart
import email.mime.text
import socket
import ssl
import sys
from pathlib import Path

import pytest

from aiosmtplib import SMTP, SMTPStatus
from aiosmtplib.sync import shutdown_loop

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
    old_loop = event_loop_policy.get_event_loop()
    loop = event_loop_policy.new_event_loop()
    event_loop_policy.set_event_loop(loop)

    def handle_async_exception(loop, context):
        """Fail on exceptions by default"""
        pytest.fail("{}: {}".format(context["message"], repr(context["exception"])))

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
    """Server side address for socket binding
    """
    return request.config.getoption("--bind-addr")


@pytest.fixture(scope="function")
def port(request, unused_tcp_port):
    """Alias for ununsed_tcp_port."""
    return unused_tcp_port


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
def message(request):
    message = email.mime.multipart.MIMEMultipart()
    message["To"] = "recipient@example.com"
    message["From"] = "sender@example.com"
    message["Subject"] = "A message"
    message.attach(email.mime.text.MIMEText("Hello World"))

    return message


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
    port,
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
            factory, host=bind_address, port=port, family=socket.AF_INET
        )
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def smtpd_server_smtputf8(
    request,
    event_loop,
    bind_address,
    hostname,
    port,
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
            factory, host=bind_address, port=port, family=socket.AF_INET
        )
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


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
def smtpd_response_handler(request):
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
def smtp_client(request, event_loop, hostname, port):
    client = SMTP(hostname=hostname, port=port, timeout=1.0)

    return client


class EchoServerProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self.transport.write(data)


@pytest.fixture(scope="function")
def echo_server(request, bind_address, port, event_loop):
    server = event_loop.run_until_complete(
        event_loop.create_server(
            EchoServerProtocol, host=bind_address, port=port, family=socket.AF_INET
        )
    )

    def close_server():
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)


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

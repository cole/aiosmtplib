"""
Pytest fixtures and config.
"""
import asyncio
import email.header
import email.message
import email.mime.multipart
import email.mime.text
from logging import Handler
import socket
import ssl
import sys
import traceback
from pathlib import Path
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)

import hypothesis
import pytest
from aiosmtpd.controller import Controller as SMTPDController
from aiosmtpd.smtp import SMTP as SMTPD

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


def pytest_addoption(parser) -> None:
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
def event_loop_policy(
    request: pytest.FixtureRequest,
) -> asyncio.AbstractEventLoopPolicy:
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
def event_loop(
    request: pytest.FixtureRequest, event_loop_policy: asyncio.AbstractEventLoopPolicy
) -> asyncio.AbstractEventLoop:
    verbosity = request.config.getoption("verbose", default=0)
    old_loop = event_loop_policy.get_event_loop()
    loop = event_loop_policy.new_event_loop()
    event_loop_policy.set_event_loop(loop)

    def handle_async_exception(
        loop: asyncio.AbstractEventLoop, context: Dict[str, Any]
    ) -> None:
        message = f'{context["message"]}: {context["exception"]!r}'
        if verbosity > 1:
            message += "\n"
            message += f"Future: {context['future']!r}"
            message += "\nTraceback:\n"
            message += "".join(traceback.format_list(context["source_traceback"]))

        request.node.warn(AsyncPytestWarning(message))

    loop.set_exception_handler(handle_async_exception)

    def cleanup() -> None:
        shutdown_loop(loop)
        event_loop_policy.set_event_loop(old_loop)

    request.addfinalizer(cleanup)

    return loop


@pytest.fixture(scope="session")
def hostname() -> str:
    return "localhost"


@pytest.fixture(scope="session")
def bind_address(request: pytest.FixtureRequest) -> str:
    """Server side address for socket binding"""
    address: str = request.config.getoption("--bind-addr")
    return address


@pytest.fixture(
    scope="function",
    params=(
        str,
        bytes,
        pytest.param(
            Path,
            marks=pytest.mark.xfail(
                sys.version_info < (3, 7),
                reason="os.PathLike support introduced in 3.7.",
            ),
        ),
    ),
    ids=("str", "bytes", "pathlike"),
)
def socket_path(
    request: pytest.FixtureRequest, tmp_path: Path
) -> Union[str, bytes, Path]:
    if sys.platform.startswith("darwin"):
        # Work around OSError: AF_UNIX path too long
        tmp_dir = Path("/tmp")  # nosec
    else:
        tmp_dir = tmp_path

    index = 0
    socket_path = tmp_dir / f"aiosmtplib-test{index}"
    while socket_path.exists():
        index += 1
        socket_path = tmp_dir / f"aiosmtplib-test{index}"

    typed_socket_path: Union[str, bytes, Path] = request.param(socket_path)

    return typed_socket_path


@pytest.fixture(scope="function")
def compat32_message() -> email.message.Message:
    message = email.message.Message()
    message["To"] = email.header.Header("recipient@example.com")
    message["From"] = email.header.Header("sender@example.com")
    message["Subject"] = "A message"
    message.set_payload("Hello World")

    return message


@pytest.fixture(scope="function")
def mime_message() -> email.mime.multipart.MIMEMultipart:
    message = email.mime.multipart.MIMEMultipart()
    message["To"] = "recipient@example.com"
    message["From"] = "sender@example.com"
    message["Subject"] = "A message"
    message.attach(email.mime.text.MIMEText("Hello World"))

    return message


@pytest.fixture(scope="function", params=["mime_multipart", "compat32"])
def message(
    request: pytest.FixtureRequest,
    compat32_message: email.message.Message,
    mime_message: email.message.EmailMessage,
) -> Union[email.message.Message, email.message.EmailMessage]:
    if request.param == "compat32":
        return compat32_message
    else:
        return mime_message


@pytest.fixture(scope="session")
def recipient_str() -> str:
    return "recipient@example.com"


@pytest.fixture(scope="session")
def sender_str() -> str:
    return "sender@example.com"


@pytest.fixture(scope="session")
def message_str(recipient_str: str, sender_str: str) -> str:
    return (
        "Content-Type: multipart/mixed; "
        'boundary="===============6842273139637972052=="\n'
        "MIME-Version: 1.0\n"
        f"To: {recipient_str}\n"
        f"From: {sender_str}\n"
        "Subject: A message\n\n"
        "--===============6842273139637972052==\n"
        'Content-Type: text/plain; charset="us-ascii"\n'
        "MIME-Version: 1.0\n"
        "Content-Transfer-Encoding: 7bit\n\n"
        "Hello World\n"
        "--===============6842273139637972052==--\n"
    )


@pytest.fixture(scope="function")
def received_messages() -> List[email.message.EmailMessage]:
    return []


@pytest.fixture(scope="function")
def received_commands() -> List[Tuple[str, ...]]:
    return []


@pytest.fixture(scope="function")
def smtpd_responses() -> List[str]:
    return []


@pytest.fixture(scope="function")
def smtpd_handler(
    received_messages: List[email.message.EmailMessage],
    received_commands: List[Tuple[str, ...]],
    smtpd_responses: List[str],
) -> RecordingHandler:
    return RecordingHandler(received_messages, received_commands, smtpd_responses)


@pytest.fixture(scope="session")
def smtpd_class() -> Type[SMTPD]:
    return TestSMTPD


@pytest.fixture(scope="session")
def valid_cert_path() -> str:
    return str(BASE_CERT_PATH.joinpath("selfsigned.crt"))


@pytest.fixture(scope="session")
def valid_key_path() -> str:
    return str(BASE_CERT_PATH.joinpath("selfsigned.key"))


@pytest.fixture(scope="session")
def invalid_cert_path() -> str:
    return str(BASE_CERT_PATH.joinpath("invalid.crt"))


@pytest.fixture(scope="session")
def invalid_key_path() -> str:
    return str(BASE_CERT_PATH.joinpath("invalid.key"))


@pytest.fixture(scope="session")
def client_tls_context(valid_cert_path: str, valid_key_path: str) -> ssl.SSLContext:
    tls_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    tls_context.load_cert_chain(valid_cert_path, keyfile=valid_key_path)
    tls_context.check_hostname = False
    tls_context.verify_mode = ssl.CERT_NONE

    return tls_context


@pytest.fixture(scope="session")
def server_tls_context(valid_cert_path: str, valid_key_path: str) -> ssl.SSLContext:
    tls_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    tls_context.load_cert_chain(valid_cert_path, keyfile=valid_key_path)

    return tls_context


@pytest.fixture(scope="session")
def auth_username() -> str:
    return "test"


@pytest.fixture(scope="session")
def auth_password() -> str:
    return "test"


@pytest.fixture(scope="session")
def smtpd_auth_callback(
    auth_username: str, auth_password: str
) -> Callable[[str, bytes, bytes], bool]:
    def auth_callback(mechanism: str, username: bytes, password: bytes) -> bool:
        return bool(
            username.decode("utf-8") == auth_username
            and password.decode("utf-8") == auth_password
        )

    return auth_callback


@pytest.fixture(scope="function")
def smtpd_server(
    request: pytest.FixtureRequest,
    event_loop: asyncio.AbstractEventLoop,
    bind_address: str,
    hostname: str,
    smtpd_class: Type[SMTPD],
    smtpd_handler: Handler,
    server_tls_context: ssl.SSLContext,
    smtpd_auth_callback: Callable[[str, bytes, bytes], bool],
) -> asyncio.AbstractServer:
    def factory() -> SMTPD:
        return smtpd_class(
            smtpd_handler,
            hostname=hostname,
            enable_SMTPUTF8=False,
            tls_context=server_tls_context,
            auth_callback=smtpd_auth_callback,
        )

    server = event_loop.run_until_complete(
        event_loop.create_server(
            factory, host=bind_address, port=0, family=socket.AF_INET
        )
    )

    def close_server() -> None:
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def smtpd_server_port(smtpd_server: asyncio.AbstractServer) -> Optional[int]:
    if smtpd_server.sockets:
        return int(smtpd_server.sockets[0].getsockname()[1])

    return None


@pytest.fixture(scope="function")
def smtpd_server_smtputf8(
    request: pytest.FixtureRequest,
    event_loop: asyncio.AbstractEventLoop,
    bind_address: str,
    hostname: str,
    smtpd_class: Type[SMTPD],
    smtpd_handler: Handler,
    server_tls_context: ssl.SSLContext,
    smtpd_auth_callback: Callable[[str, bytes, bytes], bool],
) -> asyncio.AbstractServer:
    def factory() -> SMTPD:
        return smtpd_class(
            smtpd_handler,
            hostname=hostname,
            enable_SMTPUTF8=True,
            tls_context=server_tls_context,
            auth_callback=smtpd_auth_callback,
        )

    server = event_loop.run_until_complete(
        event_loop.create_server(
            factory, host=bind_address, port=0, family=socket.AF_INET
        )
    )

    def close_server() -> None:
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def smtpd_server_smtputf8_port(
    smtpd_server_smtputf8: asyncio.AbstractServer,
) -> Optional[int]:
    if smtpd_server_smtputf8.sockets:
        return int(smtpd_server_smtputf8.sockets[0].getsockname()[1])
    return None


@pytest.fixture(scope="function")
def smtpd_server_socket_path(
    request: pytest.FixtureRequest,
    event_loop: asyncio.AbstractEventLoop,
    hostname: str,
    socket_path: Union[str, bytes, Path],
    smtpd_class: Type[SMTPD],
    smtpd_handler: Handler,
    server_tls_context: ssl.SSLContext,
    smtpd_auth_callback: Callable[[str, bytes, bytes], bool],
) -> asyncio.AbstractServer:
    def factory() -> SMTPD:
        return smtpd_class(
            smtpd_handler,
            hostname=hostname,
            enable_SMTPUTF8=False,
            tls_context=server_tls_context,
            auth_callback=smtpd_auth_callback,
        )

    create_server_coro = event_loop.create_unix_server(
        factory,
        path=socket_path,  # type: ignore
    )
    server = event_loop.run_until_complete(create_server_coro)

    def close_server() -> None:
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="session")
def smtpd_response_handler_factory() -> Callable[
    [Optional[str], Optional[str], bool, bool],
    Callable[[SMTPD], Coroutine[Any, Any, None]],
]:
    def smtpd_response(
        response_text: Optional[str],
        second_response_text: Optional[str],
        write_eof: bool,
        close_after: bool,
    ) -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
        async def response_handler(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
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
def smtp_client(hostname: str, smtpd_server_port: int) -> SMTP:
    client = SMTP(hostname=hostname, port=smtpd_server_port, timeout=1.0)

    return client


@pytest.fixture(scope="function")
def smtp_client_smtputf8(hostname: str, smtpd_server_smtputf8_port: int) -> SMTP:
    client = SMTP(hostname=hostname, port=smtpd_server_smtputf8_port, timeout=1.0)

    return client


class EchoServerProtocol(asyncio.Protocol):
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport

    def data_received(self, data: bytes) -> None:
        self.transport.write(data)  # type: ignore


@pytest.fixture(scope="function")
def echo_server(
    request: pytest.FixtureRequest,
    bind_address: str,
    event_loop: asyncio.AbstractEventLoop,
) -> asyncio.AbstractServer:
    server = event_loop.run_until_complete(
        event_loop.create_server(
            EchoServerProtocol, host=bind_address, port=0, family=socket.AF_INET
        )
    )

    def close_server() -> None:
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def echo_server_port(echo_server: asyncio.AbstractServer) -> Optional[int]:
    if echo_server.sockets:
        return int(echo_server.sockets[0].getsockname()[1])
    return None


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
def error_code(request: pytest.FixtureRequest) -> int:
    param = request.param
    return int(param)


@pytest.fixture(scope="function")
def tls_smtpd_server(
    request: pytest.FixtureRequest,
    event_loop: asyncio.AbstractEventLoop,
    bind_address: str,
    smtpd_class: Type[SMTPD],
    smtpd_handler: Handler,
    server_tls_context: ssl.SSLContext,
) -> asyncio.AbstractServer:
    def factory() -> SMTPD:
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

    def close_server() -> None:
        server.close()
        event_loop.run_until_complete(server.wait_closed())

    request.addfinalizer(close_server)

    return server


@pytest.fixture(scope="function")
def tls_smtpd_server_port(tls_smtpd_server: asyncio.AbstractServer) -> Optional[int]:
    if tls_smtpd_server.sockets:
        return int(tls_smtpd_server.sockets[0].getsockname()[1])
    return None


@pytest.fixture(scope="function")
def tls_smtp_client(hostname: str, tls_smtpd_server_port: int) -> SMTP:
    tls_client = SMTP(
        hostname=hostname,
        port=tls_smtpd_server_port,
        use_tls=True,
        validate_certs=False,
    )

    return tls_client


@pytest.fixture(scope="function")
def threaded_smtpd_server(
    request: pytest.FixtureRequest, bind_address: str, smtpd_handler: Handler
) -> asyncio.AbstractServer:
    controller = SMTPDController(smtpd_handler, hostname=bind_address, port=0)
    controller.start()
    request.addfinalizer(controller.stop)

    server: asyncio.AbstractServer = controller.server

    return server


@pytest.fixture(scope="function")
def threaded_smtpd_server_port(
    threaded_smtpd_server: asyncio.AbstractServer,
) -> Optional[int]:
    if threaded_smtpd_server.sockets:
        return int(threaded_smtpd_server.sockets[0].getsockname()[1])
    return None


@pytest.fixture(scope="function")
def smtp_client_threaded(hostname: str, threaded_smtpd_server_port: int) -> SMTP:
    client = SMTP(hostname=hostname, port=threaded_smtpd_server_port, timeout=1.0)

    return client

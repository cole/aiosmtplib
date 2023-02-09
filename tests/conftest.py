"""
Pytest fixtures and config.
"""
import asyncio
import email.header
import email.message
import email.mime.multipart
import email.mime.text
import pathlib
import socket
import ssl
import sys
from pathlib import Path
from typing import Any, Callable, Coroutine, List, Optional, Tuple, Type, Union

import hypothesis
import pytest
import trustme
from aiosmtpd.controller import Controller as SMTPDController
from aiosmtpd.smtp import SMTP as SMTPD

from aiosmtplib import SMTP, SMTPStatus

from .auth import DummySMTPAuth
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


class ParamFixtureRequest(pytest.FixtureRequest):
    param: Any


class AsyncPytestWarning(pytest.PytestWarning):
    pass


class EchoServerProtocol(asyncio.Protocol):
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport

    def data_received(self, data: bytes) -> None:
        self.transport.write(data)  # type: ignore


def pytest_addoption(parser: Any) -> None:
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
        help="address to bind on for network tests",
    )


original_event_loop_policy = None


def pytest_sessionstart(session: pytest.Session) -> None:
    global original_event_loop_policy

    # Install the uvloop event loop policy globally, per session
    loop_type = session.config.getoption("--event-loop")
    if loop_type == "uvloop":
        if not HAS_UVLOOP:
            raise RuntimeError("uvloop not installed.")
        original_event_loop_policy = asyncio.get_event_loop_policy()
        policy = uvloop.EventLoopPolicy()
        asyncio.set_event_loop_policy(policy)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if original_event_loop_policy is not None:
        asyncio.set_event_loop_policy(original_event_loop_policy)


# Session scoped static values #


@pytest.fixture(scope="session")
def bind_address(request: pytest.FixtureRequest) -> str:
    """Server side address for socket binding"""
    return str(request.config.getoption("--bind-addr"))


@pytest.fixture(scope="session")
def hostname(bind_address: str) -> str:
    return bind_address


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


@pytest.fixture(scope="session")
def smtpd_class() -> Type[SMTPD]:
    return TestSMTPD


@pytest.fixture(scope="session")
def cert_authority() -> trustme.CA:
    return trustme.CA()


@pytest.fixture(scope="session")
def unknown_cert_authority() -> trustme.CA:
    return trustme.CA()


@pytest.fixture(scope="session")
def valid_server_cert(cert_authority: trustme.CA, hostname: str) -> trustme.LeafCert:
    return cert_authority.issue_cert(hostname)


@pytest.fixture(scope="session")
def valid_client_cert(cert_authority: trustme.CA, hostname: str) -> trustme.LeafCert:
    return cert_authority.issue_cert(f"user@{hostname}")


@pytest.fixture(scope="session")
def unknown_client_cert(
    unknown_cert_authority: trustme.CA, hostname: str
) -> trustme.LeafCert:
    return unknown_cert_authority.issue_cert(f"user@{hostname}")


@pytest.fixture(scope="session")
def client_tls_context(
    cert_authority: trustme.CA, valid_client_cert: trustme.LeafCert
) -> ssl.SSLContext:
    tls_context = ssl.create_default_context()
    cert_authority.configure_trust(tls_context)
    valid_client_cert.configure_cert(tls_context)

    return tls_context


@pytest.fixture(scope="session")
def unknown_client_tls_context(
    unknown_cert_authority: trustme.CA, unknown_client_cert: trustme.LeafCert
) -> ssl.SSLContext:
    tls_context = ssl.create_default_context()
    unknown_cert_authority.configure_trust(tls_context)
    unknown_client_cert.configure_cert(tls_context)

    return tls_context


@pytest.fixture(scope="session")
def server_tls_context(
    cert_authority: trustme.CA, valid_server_cert: trustme.LeafCert
) -> ssl.SSLContext:
    tls_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    cert_authority.configure_trust(tls_context)
    valid_server_cert.configure_cert(tls_context)
    tls_context.verify_mode = ssl.CERT_OPTIONAL

    return tls_context


@pytest.fixture(scope="function")
def ca_cert_path(tmp_path: pathlib.Path, cert_authority: trustme.CA) -> str:
    cert_authority.cert_pem.write_to_path(tmp_path / "ca.pem")

    return str(tmp_path / "ca.pem")


@pytest.fixture(scope="function")
def valid_cert_path(tmp_path: pathlib.Path, valid_client_cert: trustme.LeafCert) -> str:
    for pem in valid_client_cert.cert_chain_pems:
        pem.write_to_path(tmp_path / "valid.pem", append=True)

    return str(tmp_path / "valid.pem")


@pytest.fixture(scope="function")
def valid_key_path(tmp_path: pathlib.Path, valid_client_cert: trustme.LeafCert) -> str:
    valid_client_cert.private_key_pem.write_to_path(tmp_path / "valid.key")

    return str(tmp_path / "valid.key")


@pytest.fixture(scope="function")
def invalid_cert_path(
    tmp_path: pathlib.Path, unknown_client_cert: trustme.LeafCert
) -> str:
    for pem in unknown_client_cert.cert_chain_pems:
        pem.write_to_path(tmp_path / "invalid.pem", append=True)

    return str(tmp_path / "invalid.pem")


@pytest.fixture(scope="function")
def invalid_key_path(
    tmp_path: pathlib.Path, unknown_client_cert: trustme.LeafCert
) -> str:
    unknown_client_cert.private_key_pem.write_to_path(tmp_path / "invalid.key")
    return str(tmp_path / "invalid.key")


@pytest.fixture(scope="session")
def auth_username() -> str:
    return "test"


@pytest.fixture(scope="session")
def auth_password() -> str:
    return "test"


# Error code params #


@pytest.fixture(
    scope="function",
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
def error_code(request: ParamFixtureRequest) -> int:
    return int(request.param.value)


# Auth #


@pytest.fixture(scope="function")
def mock_auth() -> DummySMTPAuth:
    return DummySMTPAuth()


# Messages #


@pytest.fixture(scope="function")
def compat32_message(recipient_str: str, sender_str: str) -> email.message.Message:
    message = email.message.Message()
    message["To"] = email.header.Header(recipient_str)
    message["From"] = email.header.Header(sender_str)
    message["Subject"] = "A message"
    message.set_payload("Hello World")

    return message


@pytest.fixture(scope="function")
def mime_message(
    recipient_str: str, sender_str: str
) -> email.mime.multipart.MIMEMultipart:
    message = email.mime.multipart.MIMEMultipart()
    message["To"] = recipient_str
    message["From"] = sender_str
    message["Subject"] = "A message"
    message.attach(email.mime.text.MIMEText("Hello World"))

    return message


@pytest.fixture(scope="function", params=["mime_multipart", "compat32"])
def message(
    request: ParamFixtureRequest,
    compat32_message: email.message.Message,
    mime_message: email.message.EmailMessage,
) -> Union[email.message.Message, email.message.EmailMessage]:
    if request.param == "compat32":
        return compat32_message
    else:
        return mime_message


# Server helpers and factories #


@pytest.fixture(scope="function")
def received_messages() -> List[email.message.EmailMessage]:
    return []


@pytest.fixture(scope="function")
def received_commands() -> List[Tuple[str, Tuple[Any, ...]]]:
    return []


@pytest.fixture(scope="function")
def smtpd_responses() -> List[str]:
    return []


@pytest.fixture(scope="function")
def smtpd_handler(
    received_messages: List[email.message.EmailMessage],
    received_commands: List[Tuple[str, Tuple[Any, ...]]],
    smtpd_responses: List[str],
) -> RecordingHandler:
    return RecordingHandler(received_messages, received_commands, smtpd_responses)


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


# Mock response #


@pytest.fixture(scope="session")
def smtpd_mock_response_delayed_ok() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_delayed_ok(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(1.0)
        await smtpd.push("250 all done")

    return mock_response_delayed_ok


@pytest.fixture(scope="session")
def smtpd_mock_response_delayed_read() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_delayed_read(
        smtpd: SMTPD, *args: Any, **kwargs: Any
    ) -> None:
        await smtpd.push("220-hi")
        await asyncio.sleep(1.0)

    return mock_response_delayed_read


@pytest.fixture(scope="session")
def smtpd_mock_response_done() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_done(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
        if args and args[0]:
            smtpd.session.host_name = args[0]
        await smtpd.push("250 done")

    return mock_response_done


@pytest.fixture(scope="session")
def smtpd_mock_response_done_then_close() -> (
    Callable[[SMTPD], Coroutine[Any, Any, None]]
):
    async def mock_response_done_then_close(
        smtpd: SMTPD, *args: Any, **kwargs: Any
    ) -> None:
        if args and args[0]:
            smtpd.session.host_name = args[0]
        await smtpd.push("250 done")
        await smtpd.push("221 bye now")
        await smtpd.transport.close()

    return mock_response_done_then_close


@pytest.fixture(scope="session")
def smtpd_mock_response_error() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_error(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
        await smtpd.push("555 error")

    return mock_response_error


@pytest.fixture(scope="session")
def smtpd_mock_response_error_disconnect() -> (
    Callable[[SMTPD], Coroutine[Any, Any, None]]
):
    async def mock_response_error_disconnect(
        smtpd: SMTPD, *args: Any, **kwargs: Any
    ) -> None:
        await smtpd.push("501 error")
        await smtpd.transport.close()

    return mock_response_error_disconnect


@pytest.fixture(scope="session")
def smtpd_mock_response_bad_data() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_bad_data(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
        smtpd._writer.write(b"250 \xFF\xFF\xFF\xFF\r\n")
        await smtpd._writer.drain()

    return mock_response_bad_data


@pytest.fixture(scope="session")
def smtpd_mock_response_gibberish() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_gibberish(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
        smtpd._writer.write("wefpPSwrsfa2sdfsdf")
        await smtpd._writer.drain()

    return mock_response_gibberish


@pytest.fixture(scope="session")
def smtpd_mock_response_expn() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_expn(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
        await smtpd.push(
            """250-Joseph Blow <jblow@example.com>
250 Alice Smith <asmith@example.com>"""
        )

    return mock_response_expn


@pytest.fixture(scope="session")
def smtpd_mock_response_ehlo_minimal() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_ehlo(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
        if args and args[0]:
            smtpd.session.host_name = args[0]

        await smtpd.push("250 HELP")

    return mock_response_ehlo


@pytest.fixture(scope="session")
def smtpd_mock_response_ehlo_full() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_ehlo(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
        if args and args[0]:
            smtpd.session.host_name = args[0]

        await smtpd.push(
            """250-localhost
250-PIPELINING
250-8BITMIME
250-SIZE 512000
250-DSN
250-ENHANCEDSTATUSCODES
250-EXPN
250-HELP
250-SAML
250-SEND
250-SOML
250-TURN
250-XADR
250-XSTA
250-ETRN
250 XGEN"""
        )

    return mock_response_ehlo


@pytest.fixture(scope="session")
def smtpd_mock_response_unavailable() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_unavailable(
        smtpd: SMTPD, *args: Any, **kwargs: Any
    ) -> None:
        await smtpd.push("421 retry in 5 minutes")
        await smtpd.transport.close()

    return mock_response_unavailable


@pytest.fixture(scope="session")
def smtpd_mock_response_tls_not_available() -> (
    Callable[[SMTPD], Coroutine[Any, Any, None]]
):
    async def mock_tls_not_available(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
        await smtpd.push("454 please login")

    return mock_tls_not_available


@pytest.fixture(scope="session")
def smtpd_mock_response_tls_ready_disconnect() -> (
    Callable[[SMTPD], Coroutine[Any, Any, None]]
):
    async def mock_response_tls_ready_disconnect(
        smtpd: SMTPD, *args: Any, **kwargs: Any
    ) -> None:
        await smtpd.push("220 go for it")
        await smtpd.transport.close()

    return mock_response_tls_ready_disconnect


@pytest.fixture(scope="session")
def smtpd_mock_response_disconnect() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_disconnect(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
        await smtpd.transport.close()

    return mock_response_disconnect


@pytest.fixture(scope="session")
def smtpd_mock_response_eof() -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    async def mock_response_eof(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
        await smtpd.transport.write_eof()

    return mock_response_eof


@pytest.fixture(scope="session")
def smtpd_mock_response_error_with_code_factory() -> (
    Callable[[str], Callable[[SMTPD], Coroutine[Any, Any, None]]]
):
    def factory(error_code: str) -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
        async def mock_error_response(smtpd: SMTPD, *args: Any, **kwargs: Any) -> None:
            await smtpd.push(f"{error_code} error")

        return mock_error_response

    return factory


@pytest.fixture(scope="function")
def smtpd_mock_response_error_with_code(
    error_code: int,
    smtpd_mock_response_error_with_code_factory: Callable[
        [str], Callable[[SMTPD], Coroutine[Any, Any, None]]
    ],
) -> Callable[[SMTPD], Coroutine[Any, Any, None]]:
    return smtpd_mock_response_error_with_code_factory(str(error_code))


@pytest.fixture(
    scope="function",
    params=(str, bytes, Path),
    ids=("str", "bytes", "pathlike"),
)
def socket_path(
    request: ParamFixtureRequest, tmp_path: Path
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


# Servers #


@pytest.fixture(scope="function")
def smtpd_server(
    request: pytest.FixtureRequest,
    event_loop: asyncio.AbstractEventLoop,
    bind_address: str,
    hostname: str,
    smtpd_class: Type[SMTPD],
    smtpd_handler: RecordingHandler,
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
def smtpd_server_smtputf8(
    request: pytest.FixtureRequest,
    event_loop: asyncio.AbstractEventLoop,
    bind_address: str,
    hostname: str,
    smtpd_class: Type[SMTPD],
    smtpd_handler: RecordingHandler,
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
def smtpd_server_socket_path(
    request: pytest.FixtureRequest,
    event_loop: asyncio.AbstractEventLoop,
    hostname: str,
    socket_path: Union[str, bytes, Path],
    smtpd_class: Type[SMTPD],
    smtpd_handler: RecordingHandler,
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


@pytest.fixture(scope="function")
def smtpd_server_tls(
    request: pytest.FixtureRequest,
    event_loop: asyncio.AbstractEventLoop,
    bind_address: str,
    smtpd_class: Type[SMTPD],
    smtpd_handler: RecordingHandler,
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
def smtpd_controller(
    request: pytest.FixtureRequest,
    bind_address: str,
    unused_tcp_port: int,
    smtpd_handler: RecordingHandler,
) -> SMTPDController:
    port = unused_tcp_port
    controller: Optional[SMTPDController]
    controller = SMTPDController(smtpd_handler, hostname=bind_address, port=port)
    controller.start()

    request.addfinalizer(controller.stop)

    return controller


@pytest.fixture(scope="function")
def smtpd_server_threaded(
    request: pytest.FixtureRequest, smtpd_controller: SMTPDController
) -> asyncio.AbstractServer:
    server: asyncio.AbstractServer = smtpd_controller.server
    return server


# Running server ports #


def _get_server_socket_port(server: asyncio.AbstractServer) -> Optional[int]:
    sockets = getattr(server, "sockets", [])
    if sockets:
        return int(sockets[0].getsockname()[1])

    return None


@pytest.fixture(scope="function")
def smtpd_server_port(smtpd_server: asyncio.AbstractServer) -> Optional[int]:
    return _get_server_socket_port(smtpd_server)


@pytest.fixture(scope="function")
def smtpd_server_smtputf8_port(
    smtpd_server_smtputf8: asyncio.AbstractServer,
) -> Optional[int]:
    return _get_server_socket_port(smtpd_server_smtputf8)


@pytest.fixture(scope="function")
def echo_server_port(echo_server: asyncio.AbstractServer) -> Optional[int]:
    return _get_server_socket_port(echo_server)


@pytest.fixture(scope="function")
def smtpd_server_tls_port(smtpd_server_tls: asyncio.AbstractServer) -> Optional[int]:
    return _get_server_socket_port(smtpd_server_tls)


@pytest.fixture(scope="function")
def smtpd_server_threaded_port(smtpd_controller: SMTPDController) -> int:
    port: int = smtpd_controller.port
    return port


# SMTP Clients #


@pytest.fixture(scope="function")
def smtp_client(
    hostname: str, smtpd_server_port: int, client_tls_context: ssl.SSLContext
) -> SMTP:
    return SMTP(
        hostname=hostname,
        port=smtpd_server_port,
        tls_context=client_tls_context,
        start_tls=False,
        timeout=1.0,
    )


@pytest.fixture(scope="function")
def smtp_client_smtputf8(
    hostname: str, smtpd_server_smtputf8_port: int, client_tls_context: ssl.SSLContext
) -> SMTP:
    return SMTP(
        hostname=hostname,
        port=smtpd_server_smtputf8_port,
        timeout=1.0,
        start_tls=False,
        tls_context=client_tls_context,
    )


@pytest.fixture(scope="function")
def smtp_client_tls(
    hostname: str, smtpd_server_tls_port: int, client_tls_context: ssl.SSLContext
) -> SMTP:
    return SMTP(
        hostname=hostname,
        port=smtpd_server_tls_port,
        use_tls=True,
        tls_context=client_tls_context,
    )


@pytest.fixture(scope="function")
def smtp_client_threaded(
    hostname: str, smtpd_server_threaded_port: int, client_tls_context: ssl.SSLContext
) -> SMTP:
    return SMTP(
        hostname=hostname,
        port=smtpd_server_threaded_port,
        timeout=1.0,
        start_tls=False,
        tls_context=client_tls_context,
    )

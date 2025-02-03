import email.message
import ssl
import sys
from typing import Any

import pytest

from aiosmtplib import send

IS_PYPY = hasattr(sys, "pypy_version_info")


def filter_leaks(stack) -> bool:
    leaker_filenames = ["aiosmtpd", "ssl.py", "sslproto.py"]
    for frame in stack.frames:
        if any([leaker in frame.filename for leaker in leaker_filenames]):
            return False
        elif "ssl" in frame.function:
            return False

    return True


@pytest.mark.slow
@pytest.mark.skipif(IS_PYPY, reason="PyPy is not supported")
@pytest.mark.limit_leaks("64 KB", filter_fn=filter_leaks)
async def test_send_memory_leaks(
    hostname: str,
    smtpd_server_port: int,
    mime_message: email.message.EmailMessage,
    received_messages: list[email.message.EmailMessage],
    received_commands: list[tuple[str, tuple[Any, ...]]],
    smtpd_responses: list[str],
    client_tls_context: ssl.SSLContext,
) -> None:
    for _ in range(100):
        errors, response = await send(
            mime_message,
            hostname=hostname,
            port=smtpd_server_port,
            tls_context=client_tls_context,
        )

        assert not errors

    assert len(received_messages) == 100

    # Clear or these will add to our "leaks"
    received_messages.clear()
    received_commands.clear()
    smtpd_responses.clear()

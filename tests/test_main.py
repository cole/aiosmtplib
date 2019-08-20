import asyncio
import sys

import pytest


pytestmark = pytest.mark.asyncio()


async def test_command_line_send(hostname, smtpd_server_port):
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        b"-m",
        b"aiosmtplib",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )

    inputs = (
        bytes(hostname, "ascii"),
        bytes(str(smtpd_server_port), "ascii"),
        b"sender@example.com",
        b"recipient@example.com",
        b"Subject: Hello World\n\nHi there.",
    )
    messages = (
        b"SMTP server hostname [localhost]:",
        b"SMTP server port [25]:",
        b"From:",
        b"To:",
        b"Enter message, end with ^D:",
    )

    output, errors = await proc.communicate(input=b"\n".join(inputs))

    assert errors is None
    for message in messages:
        assert message in output

    assert proc.returncode == 0

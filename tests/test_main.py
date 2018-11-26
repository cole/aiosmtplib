import asyncio
import sys

import pytest


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_command_line_send(event_loop, smtpd_server, hostname, port):
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        b"-m",
        b"aiosmtplib",
        loop=event_loop,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )

    expected = (
        (b"hostname", bytes(hostname, "ascii")),
        (b"port", bytes(str(port), "ascii")),
        (b"From", b"sender@example.com"),
        (b"To", b"recipient@example.com"),
        (b"message", b"Subject: Hello World\n\nHi there."),
    )

    for expected_output, write_bytes in expected:
        output = await proc.stdout.readuntil(separator=b":")
        assert expected_output in output
        proc.stdin.write(write_bytes + b"\n")
        await proc.stdin.drain()

    proc.stdin.write_eof()
    await proc.stdin.drain()

    return_code = await proc.wait()
    assert return_code == 0

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

    output = await proc.stdout.readuntil(separator=b":")
    assert b"hostname" in output
    proc.stdin.write(bytes(hostname, "ascii") + b"\n")
    await proc.stdin.drain()

    output = await proc.stdout.readuntil(separator=b":")
    assert b"port" in output
    port = bytes(str(port), "ascii") + b"\n"
    proc.stdin.write(port)
    await proc.stdin.drain()

    output = await proc.stdout.readuntil(separator=b":")
    assert b"From" in output
    proc.stdin.write(b"sender@example.com\n")
    await proc.stdin.drain()

    output = await proc.stdout.readuntil(separator=b":")
    assert b"To" in output
    proc.stdin.write(b"recipient@example.com\n")
    await proc.stdin.drain()

    output = await proc.stdout.readuntil(separator=b":")
    assert b"message" in output
    proc.stdin.write(b"Subject: Hello World\n\nHi there.\n")
    proc.stdin.write_eof()
    await proc.stdin.drain()

    return_code = await proc.wait()
    assert return_code == 0

# pyright: strict

import email.message
import pathlib
import socket
import ssl

import aiosmtplib


async def send_str():
    await aiosmtplib.send("test")


async def send_message():
    message = email.message.EmailMessage()
    await aiosmtplib.send(message)


async def send_all_options():
    await aiosmtplib.send(
        "test",
        sender="test@example.com",
        recipients=["user1@example.com"],
        mail_options=["FOO"],
        rcpt_options=["BAR"],
        hostname="smtp.example.com",
        port=1234,
        username="root@example.com",
        password="changeme",
        local_hostname="test",
        source_address=("foo", 123),
        timeout=124.34,
        use_tls=True,
        start_tls=False,
        validate_certs=False,
        client_cert="test",
        client_key="test",
        tls_context=ssl.create_default_context(),
        cert_bundle="test",
        socket_path=pathlib.PurePath("/tmp/foo"),
        sock=socket.socket(),
    )

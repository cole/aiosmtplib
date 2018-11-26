"""
Tests that cover asyncio usage.
"""

import asyncio

import pytest

from aiosmtplib import SMTP


RECIPIENTS = [
    "recipient1@example.com",
    "recipient2@example.com",
    "recipient3@example.com",
]

pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_sendmail_multiple_times_in_sequence(smtpd_client, message):
    async with smtpd_client:
        for recipient in RECIPIENTS:
            errors, response = await smtpd_client.sendmail(
                message["From"], [recipient], str(message)
            )

            assert not errors
            assert isinstance(errors, dict)
            assert response != ""


async def test_sendmail_multiple_times_with_gather(smtpd_client, event_loop, message):
    async with smtpd_client:
        tasks = [
            smtpd_client.sendmail(message["From"], [recipient], str(message))
            for recipient in RECIPIENTS
        ]
        results = await asyncio.gather(*tasks, loop=event_loop)
        for errors, message in results:
            assert not errors
            assert isinstance(errors, dict)
            assert message != ""


async def test_connect_and_sendmail_multiple_times_with_gather(
    smtpd_server, event_loop, hostname, port, message
):
    client = SMTP(hostname=hostname, port=port, loop=event_loop)

    async def connect_and_send(*args, **kwargs):
        async with client:
            response = await client.sendmail(*args, **kwargs)

        return response

    tasks = [
        connect_and_send(message["From"], [recipient], str(message))
        for recipient in RECIPIENTS
    ]
    results = await asyncio.gather(*tasks, loop=event_loop)
    for errors, message in results:
        assert not errors
        assert isinstance(errors, dict)
        assert message != ""


async def test_multiple_clients_with_gather(smtpd_server, event_loop, hostname, port, message):
    async def connect_and_send(*args, **kwargs):
        client = SMTP(hostname=hostname, port=port, loop=event_loop)
        async with client:
            response = await client.sendmail(*args, **kwargs)

        return response

    tasks = [
        connect_and_send(message["From"], [recipient], str(message)) for recipient in RECIPIENTS
    ]
    results = await asyncio.gather(*tasks, loop=event_loop)
    for errors, message in results:
        assert not errors
        assert isinstance(errors, dict)
        assert message != ""


async def test_multiple_actions_in_context_manager_with_gather(
    smtpd_server, event_loop, hostname, port, message
):
    client = SMTP(hostname=hostname, port=port, loop=event_loop)

    async def connect_and_run_commands(*args, **kwargs):
        async with client:
            await client.ehlo()
            await client.noop()
            await client.help()
            response = await client.sendmail(*args, **kwargs)

        return response

    tasks = [
        connect_and_run_commands(message["From"], [recipient], str(message))
        for recipient in RECIPIENTS
    ]
    results = await asyncio.gather(*tasks, loop=event_loop)
    for errors, message in results:
        assert not errors
        assert isinstance(errors, dict)
        assert message != ""


async def test_many_commands_with_gather(smtpd_client, event_loop):
    """
    Without a lock on the reader, this raises RuntimeError.
    """
    async with smtpd_client:
        tasks = [
            smtpd_client.noop(),
            smtpd_client.noop(),
            smtpd_client.helo(),
            smtpd_client.vrfy("foo@bar.com"),
            smtpd_client.noop(),
        ]
        results = await asyncio.gather(*tasks, loop=event_loop)
        for result in results:
            assert 200 <= result.code < 300


async def test_close_works_on_stopped_loop(preset_server, event_loop):
    preset_client = SMTP(
        hostname=preset_server.hostname, port=preset_server.port, loop=event_loop
    )

    await preset_client.connect()
    assert preset_client.is_connected
    assert preset_client.transport is not None

    event_loop.stop()

    preset_client.close()
    assert not preset_client.is_connected

import asyncio

import pytest

from aiosmtplib import SMTP


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_sendmail_multiple_times_in_sequence(smtpd_client):
    async with smtpd_client:
        sender = 'test@example.com'
        recipients = [
            'recipient1@example.com',
            'recipient2@example.com',
            'recipient3@example.com',
        ]
        mail_text = """
        Hello world!

        -a tester
        """
        for recipient in recipients:
            errors, message = await smtpd_client.sendmail(
                sender, [recipient], mail_text)

            assert not errors
            assert isinstance(errors, dict)
            assert message != ''


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_sendmail_multiple_times_with_gather(smtpd_client):
    async with smtpd_client:
        sender = 'test@example.com'
        recipients = [
            'recipient1@example.com',
            'recipient2@example.com',
            'recipient3@example.com',
        ]
        mail_text = """
        Hello world!

        -a tester
        """
        tasks = [
            smtpd_client.sendmail(sender, [recipient], mail_text)
            for recipient in recipients
        ]
        results = await asyncio.gather(*tasks, loop=smtpd_client.loop)
        for errors, message in results:
            assert not errors
            assert isinstance(errors, dict)
            assert message != ''


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_connect_and_sendmail_multiple_times_with_gather(
        smtpd_server, event_loop):
    sender = 'test@example.com'
    recipients = [
        'recipient1@example.com',
        'recipient2@example.com',
        'recipient3@example.com',
    ]
    mail_text = """
    Hello world!

    -a tester
    """

    client = SMTP(
        hostname='127.0.0.1', port=smtpd_server.port, loop=event_loop)

    async def connect_and_send(*args, **kwargs):
        async with client:
            response = await client.sendmail(*args, **kwargs)

        return response

    tasks = [
        connect_and_send(sender, [recipient], mail_text)
        for recipient in recipients
    ]
    results = await asyncio.gather(*tasks, loop=event_loop)
    for errors, message in results:
        assert not errors
        assert isinstance(errors, dict)
        assert message != ''


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_multiple_clients_with_gather(smtpd_server, event_loop):
    sender = 'test@example.com'
    recipients = [
        'recipient1@example.com',
        'recipient2@example.com',
        'recipient3@example.com',
    ]
    mail_text = """
    Hello world!

    -a tester
    """

    async def connect_and_send(*args, **kwargs):
        client = SMTP(
            hostname='127.0.0.1', port=smtpd_server.port, loop=event_loop)
        async with client:
            response = await client.sendmail(*args, **kwargs)

        return response

    tasks = [
        connect_and_send(sender, [recipient], mail_text)
        for recipient in recipients
    ]
    results = await asyncio.gather(*tasks, loop=event_loop)
    for errors, message in results:
        assert not errors
        assert isinstance(errors, dict)
        assert message != ''


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_multiple_actions_in_context_manager_with_gather(
        smtpd_server, event_loop):
    sender = 'test@example.com'
    recipients = [
        'recipient1@example.com',
        'recipient2@example.com',
        'recipient3@example.com',
    ]
    mail_text = """
    Hello world!

    -a tester
    """

    client = SMTP(
        hostname='127.0.0.1', port=smtpd_server.port, loop=event_loop)

    async def connect_and_run_commands(*args, **kwargs):
        async with client:
            await client.ehlo()
            await client.noop()
            await client.help()
            response = await client.sendmail(*args, **kwargs)

        return response

    tasks = [
        connect_and_run_commands(sender, [recipient], mail_text)
        for recipient in recipients
    ]
    results = await asyncio.gather(*tasks, loop=event_loop)
    for errors, message in results:
        assert not errors
        assert isinstance(errors, dict)
        assert message != ''


@pytest.mark.asyncio(forbid_global_loop=True)
async def test_many_commands_with_gather(smtpd_client):
    """
    Without a lock on the reader, this raises RuntimeError.
    """
    async with smtpd_client:
        tasks = [
            smtpd_client.noop(),
            smtpd_client.noop(),
            smtpd_client.helo(),
            smtpd_client.vrfy('foo@bar.com'),
            smtpd_client.noop(),
        ]
        results = await asyncio.gather(*tasks, loop=smtpd_client.loop)
        for result in results:
            assert 200 <= result.code < 300

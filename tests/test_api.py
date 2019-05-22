"""
send_message coroutine testing.
"""
import pytest

from aiosmtplib import send_message


pytestmark = pytest.mark.asyncio()


async def test_send_message_function(
    hostname, port, smtpd_server, message, recieved_messages
):
    errors, response = await send_message(message, hostname=hostname, port=port)

    assert not errors
    assert response != ""
    assert len(recieved_messages) == 1

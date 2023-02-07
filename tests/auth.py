from collections import deque
from typing import Any, Deque, List, Tuple

from aiosmtplib.response import SMTPResponse
from aiosmtplib.smtp import SMTP


class DummySMTPAuth(SMTP):
    transport = None

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self.received_commands: List[bytes] = []
        self.responses: Deque[Tuple[int, str]] = deque()
        self.esmtp_extensions = {"auth": ""}
        self.server_auth_methods = ["cram-md5", "login", "plain"]
        self.supports_esmtp = True

    async def execute_command(self, *args: Any, **kwargs: Any) -> SMTPResponse:
        self.received_commands.append(b" ".join(args))

        response = self.responses.popleft()

        return SMTPResponse(*response)

    async def _ehlo_or_helo_if_needed(self) -> None:
        return None

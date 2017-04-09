from collections import deque

from aiosmtplib.auth import SMTPAuth
from aiosmtplib.response import SMTPResponse


class DummySMTPAuth(SMTPAuth):

    transport = None

    def __init__(self):
        self.recieved_commands = []
        self.responses = deque()
        self.esmtp_extensions = {'auth': ''}
        self.server_auth_methods = ['cram-md5', 'login', 'plain']
        self.supports_esmtp = True

    async def execute_command(self, *args, **kwargs):
        self.recieved_commands.append(b' '.join(args))

        response = self.responses.popleft()

        return SMTPResponse(*response)

    async def _ehlo_or_helo_if_needed(self):
        pass

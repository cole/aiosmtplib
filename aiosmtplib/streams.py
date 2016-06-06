import asyncio

from aiosmtplib import status
from aiosmtplib.errors import SMTPResponseException, SMTPServerDisconnected


class SMTPStreamReader(asyncio.StreamReader):

    async def read_response(self):
        '''
        Get a status reponse from the server.

        Returns a tuple consisting of:

          - server response code (e.g. '250', or such, if all goes well)
            Note: returns -1 if it can't read response code.

          - server response string corresponding to response code (multiline
            responses are converted to a single, multiline string).

        Raises SMTPResponseException for codes > 500.
        '''
        code = -1
        response_lines = []
        response_finished = False

        while not response_finished:
            try:
                line = await self.readline()
            except asyncio.LimitOverrunError:
                raise SMTPResponseException(500, "Line too long.")
            except ConnectionResetError as exc:
                raise SMTPServerDisconnected(exc)

            response_finished = (line[3:4] != b"-")

            try:
                code = int(line[:3])
            except ValueError:
                pass

            message = line[4:].strip(b' \t\r\n').decode('ascii')
            response_lines.append(message)

        full_message = "\n".join(response_lines)

        if status.is_permanent_error_code(code):
            raise SMTPResponseException(code, full_message)

        return code, message


class SMTPStreamWriter(asyncio.StreamWriter):

    async def send_command(self, *args):
        '''
        Format a command and send it to the server.
        '''
        command = "{}\r\n".format(' '.join(args)).encode('ascii')
        self.write(command)

        await self.drain()

import asyncio

from aiosmtplib import status
from aiosmtplib.errors import SMTPResponseException, SMTPServerDisconnected


class SMTPStreamReader(asyncio.StreamReader):

    async def read_response(self):
        '''
        Get a status reponse from the server.

        Returns a tuple consisting of:

          - server response code (e.g. 250, or such, if all goes well)

          - server response string corresponding to response code (multiline
            responses are converted to a single, multiline string).

        Raises SMTPResponseException for codes > 500.
        '''
        code = None
        response_lines = []

        while True:
            try:
                line = await self.readline()
            # TODO: alternative to LimitOverrunError
            # except LimitOverrunError:
            #     raise SMTPResponseException(500, "Line too long.")
            except ConnectionResetError as exc:
                raise SMTPServerDisconnected(exc)

            try:
                code = int(line[:3])
            except ValueError:
                pass

            message = line[4:].strip(b' \t\r\n').decode('ascii')
            response_lines.append(message)

            if line[3:4] != b"-":
                break

        full_message = "\n".join(response_lines)

        if code is None and self.at_eof():
            raise SMTPServerDisconnected('Server disconnected unexpectedly')
        elif code is None:
            raise SMTPResponseException(
                -1, 'Malformed SMTP response: {}'.format(full_message))
        elif status.is_permanent_error_code(code):
            raise SMTPResponseException(code, full_message)

        return code, full_message


class SMTPStreamWriter(asyncio.StreamWriter):

    async def send_command(self, *args):
        '''
        Format a command and send it to the server.
        '''
        command = "{}\r\n".format(' '.join(args)).encode('ascii')
        self.write(command)

        await self.drain()

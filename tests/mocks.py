import asyncio


class MockSMTP:
    @classmethod
    def __init__(cls, **kwargs):
        cls.kwargs = kwargs

    async def __aenter__(self, *args, **kwargs):
        return self

    async def __aexit__(self, *args, **kwargs):
        pass

    async def starttls(self, *args, **kwargs):
        pass

    async def send_message(self, *args, **kwargs):
        return {}, ""


class EchoServerProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self.transport.write(data)

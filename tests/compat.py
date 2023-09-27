import asyncio


async def cleanup_server(server: asyncio.AbstractServer) -> None:
    try:
        await asyncio.wait_for(server.wait_closed(), 0.1)
    except asyncio.TimeoutError:
        pass

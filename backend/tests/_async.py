"""Loop asyncio condiviso per i test che chiamano funzioni di server.py:
il client Motor di server vive a livello di modulo, quindi serve UN solo loop per worker."""
import asyncio

_loop = asyncio.new_event_loop()


def run(coro):
    return _loop.run_until_complete(coro)

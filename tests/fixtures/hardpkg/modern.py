import asyncio
from typing import Protocol, overload

class Reader(Protocol):
    def read(self) -> bytes: ...

@overload
def parse(x: int) -> int: ...
@overload
def parse(x: str) -> str: ...
def parse(x):
    match x:
        case int() as n if (m := n * 2) > 0:
            return m
        case str() as s:
            return s
        case _:
            return None

async def fetch(r: Reader):
    async with _ctx() as c:
        return await asyncio.sleep(0, c)

def _ctx():
    return asyncio.Lock()

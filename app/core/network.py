from __future__ import annotations
import asyncio
import socket
from typing import Iterable


async def wait_for_internet(
    hosts: Iterable[tuple[str, int]] = (("1.1.1.1", 53), ("8.8.8.8", 53)),
    timeout_sec: float = 3.0,
    check_interval_sec: float = 5.0,
) -> None:
    """
    Blocks until we can open a TCP connection to at least one host:port.
    Uses DNS ports on well-known resolvers; does not rely on HTTP.
    """
    while True:
        for host, port in hosts:
            try:
                fut = asyncio.to_thread(_probe_tcp, host, port, timeout_sec)
                ok = await fut
                if ok:
                    return
            except Exception:
                pass
        await asyncio.sleep(check_interval_sec)


def _probe_tcp(host: str, port: int, timeout_sec: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False
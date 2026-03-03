from __future__ import annotations
import asyncio
import socket
from typing import Iterable, Optional


async def wait_for_internet(
    hosts: Iterable[tuple[str, int]] = (("1.1.1.1", 53), ("8.8.8.8", 53)),
    timeout_sec: float = 3.0,
    check_interval_sec: float = 5.0,
    logger=None,
) -> None:
    """
    Blocks until we can open a TCP connection to at least one host:port.
    Logs only when we enter/exit offline state if logger is provided.
    """
    was_offline = False
    while True:
        for host, port in hosts:
            try:
                ok = await asyncio.to_thread(_probe_tcp, host, port, timeout_sec)
                if ok:
                    if was_offline and logger:
                        logger.info("Internet is back ✅ Resuming work.")
                    return
            except Exception:
                pass

        if not was_offline:
            was_offline = True
            if logger:
                logger.warning("No internet detected ❌ Waiting to reconnect...")

        await asyncio.sleep(check_interval_sec)


def _probe_tcp(host: str, port: int, timeout_sec: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False
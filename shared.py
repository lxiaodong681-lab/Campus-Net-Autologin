"""Shared constants, types, and utilities used across the project."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Optional

APP_NAME = "srun_login"
IPC_PORT_BASE = 38000
DEFAULT_GATEWAY = "172.17.1.2"

DEFAULT_TIMED_CONFIG: dict = {
    "enabled": False,
    "start_time": "07:00",
    "end_time": "23:59",
    "check_interval_connected": 600,
    "check_interval_disconnected": 120,
    "check_interval_retry": 180,
    "max_retries_per_session": 5,
}


def ipc_port(app_name: str = APP_NAME) -> int:
    digest = hashlib.md5(app_name.encode("utf-8")).hexdigest()
    return IPC_PORT_BASE + (int(digest[:6], 16) % 1000)


# ---------------------------------------------------------------------------
# Single-instance lock (moved from main.py so it can be reused)
# ---------------------------------------------------------------------------


class SingleInstanceLock:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.handle: Optional[object] = None

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.lock_path, "a+")
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def release(self) -> None:
        if not self.handle:
            return
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self.handle.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# IPC helper
# ---------------------------------------------------------------------------


def send_ipc(app_name: str, message: str) -> None:
    import socket

    port = ipc_port(app_name)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
            sock.sendall(message.encode("utf-8"))
    except OSError:
        pass

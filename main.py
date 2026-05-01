"""Main entry for the campus network auto-login tool."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
from pathlib import Path
from typing import Optional

from config_manager import ConfigManager
from gui import AppOptions, run_app
from srun_login import SRUNLogin


def _ipc_port(app_name: str) -> int:
    import hashlib

    digest = hashlib.md5(app_name.encode("utf-8")).hexdigest()
    return 38000 + (int(digest[:6], 16) % 1000)


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


def send_ipc(app_name: str, message: str) -> None:
    port = _ipc_port(app_name)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
            sock.sendall(message.encode("utf-8"))
    except OSError:
        pass


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校园网自动登录工具")
    parser.add_argument("--minimized", action="store_true", help="启动到后台")
    parser.add_argument("--background", action="store_true", help="后台静默登录并退出")
    parser.add_argument("--configure", action="store_true", help="强制显示配置界面")
    parser.add_argument("--quit", action="store_true", help="退出已运行实例")
    return parser.parse_args()


def _setup_logging() -> None:
    logs_dir = Path(__file__).with_name("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "error.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    _setup_logging()
    args = _parse_args()
    config_manager = ConfigManager()
    lock_path = config_manager.config_dir / "srun_login.lock"
    lock = SingleInstanceLock(lock_path)

    if not lock.acquire():
        if args.quit:
            send_ipc(config_manager.app_name, "quit")
        else:
            send_ipc(config_manager.app_name, "show")
        return
    try:
        if args.background:
            data = config_manager.load_config()
            username = config_manager.get_username() or data.get("username", "")
            password = config_manager.get_password() or ""
            gateway = data.get("gateway", "")
            ac_id = data.get("ac_id", "1")
            default_ip = data.get("default_ip") or None
            if not username or not password or not gateway:
                print("❌ 缺少账号、密码或网关配置，无法后台登录")
                return
            login = SRUNLogin(username, password, gateway, ac_id, ip=default_ip)
            login.login()
            return

        data = config_manager.load_config()
        if args.configure:
            options = AppOptions(start_minimized=False, auto_connect_on_start=False, app_name=config_manager.app_name)
        else:
            options = AppOptions(
                start_minimized=args.minimized or data.get("start_minimized", False),
                auto_connect_on_start=data.get("auto_connect_on_start", False),
                app_name=config_manager.app_name,
            )
        run_app(options)
    finally:
        lock.release()


if __name__ == "__main__":
    main()

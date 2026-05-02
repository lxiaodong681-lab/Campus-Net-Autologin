"""Timed login manager for long-running devices."""

from __future__ import annotations

import os
import signal
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from config_manager import ConfigManager
from srun_login import SRUNLogin


class TimedLoginManager:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config = config_manager.load_config()
        self.timed_config = self.config.get("timed_mode", {})
        self.srun: Optional[SRUNLogin] = None
        self.pid_file = Path(tempfile.gettempdir()) / "srun_login_timed.pid"
        self._register_signal_handler()

    def _register_signal_handler(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _handle_exit(self, signum, frame) -> None:
        print("[信息] 收到停止信号，正在退出...")
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except OSError:
                pass
        sys.exit(0)

    def _parse_time(self, value: str) -> datetime.time:
        return datetime.strptime(value, "%H:%M").time()

    def _is_in_active_hours(self) -> bool:
        start = self._parse_time(self.timed_config.get("start_time", "07:00"))
        end = self._parse_time(self.timed_config.get("end_time", "23:59"))
        now = datetime.now().time()
        if start <= end:
            return start <= now <= end
        return now >= start or now <= end

    def _is_network_connected(self) -> bool:
        try:
            resp = requests.get("http://www.baidu.com", timeout=5)
            return resp.status_code < 400
        except requests.RequestException:
            return False

    def _ensure_login(self) -> bool:
        data = self.config_manager.load_config()
        username = self.config_manager.get_username() or data.get("username", "")
        password = self.config_manager.get_password() or ""
        gateway = data.get("gateway", "")
        ac_id = data.get("ac_id", "1")
        default_ip = data.get("default_ip") or None
        if not username or not password or not gateway:
            print("❌ 缺少账号、密码或网关配置，无法登录")
            print("提示：请先通过图形界面配置，或手动编辑配置文件")
            return False
        if self.srun is None:
            self.srun = SRUNLogin(username, password, gateway, ac_id, ip=default_ip)
        return self.srun.login()

    def _get_interval(self, connected: bool, success: bool) -> int:
        if connected:
            return int(self.timed_config.get("check_interval_connected", 600))
        if success:
            return int(self.timed_config.get("check_interval_connected", 600))
        return int(self.timed_config.get("check_interval_disconnected", 120))

    def run_loop(self) -> None:
        retry_count = 0
        max_retries = int(self.timed_config.get("max_retries_per_session", 5))
        self.pid_file.write_text(str(os.getpid()))
        while True:
            if not self._is_in_active_hours():
                time.sleep(3600)
                retry_count = 0
                continue
            connected = self._is_network_connected()
            if connected:
                retry_count = 0
                interval = self._get_interval(connected=True, success=True)
                print(f"[定时模式] 网络畅通，下次检查 {interval} 秒后")
                time.sleep(interval)
                continue
            success = self._ensure_login()
            if success:
                retry_count = 0
                interval = self._get_interval(connected=False, success=True)
                print(f"[定时模式] 登录成功，下次检查 {interval} 秒后")
            else:
                retry_count += 1
                interval = int(self.timed_config.get("check_interval_retry", 180))
                if retry_count >= max_retries:
                    print(f"[定时模式] 登录失败次数过多，{interval} 秒后再检查")
                    retry_count = 0
                else:
                    print(f"[定时模式] 登录失败，{interval} 秒后重试")
            time.sleep(interval)

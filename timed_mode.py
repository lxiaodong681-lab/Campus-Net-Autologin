"""Timed login manager for long-running devices."""

from __future__ import annotations

import logging
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
from errors import ErrorCode
from srun_login import SRUNLogin

_LOGGER = logging.getLogger(__name__)

_INACTIVE_CHECK_INTERVAL = 60   # seconds between wake-ups during inactive hours


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
        _LOGGER.info("收到停止信号，正在退出...")
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
            _LOGGER.debug("Baidu connectivity check failed (request error)")
            return False
        except OSError:
            _LOGGER.debug("Baidu connectivity check failed (OS/DNS error)")
            return False

    def _ensure_login(self) -> bool:
        creds = self.config_manager.get_login_credentials()
        if creds is None:
            _LOGGER.error(ErrorCode.CREDENTIAL_NOT_FOUND.full_message())
            return False

        if self.srun is None:
            self.srun = SRUNLogin(
                creds.username, creds.password, creds.gateway, creds.ac_id, ip=creds.default_ip,
            )
        else:
            # Refresh credentials in case they were updated
            self.srun.username = creds.username
            self.srun.password = creds.password
            self.srun.gateway = creds.gateway
            self.srun.ac_id = creds.ac_id
            self.srun.ip = creds.default_ip

        success = self.srun.login()
        if not success:
            err = self.srun.get_last_error()
            if err:
                _LOGGER.warning(err.full_message())
            else:
                _LOGGER.warning("登录失败（未知原因）")
        return success

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
        _LOGGER.info("定时模式主循环已启动 (PID=%s)", os.getpid())

        while True:
            if not self._is_in_active_hours():
                # Sleep in short increments so SIGTERM is handled promptly
                for _ in range(60):  # 60 * 60s = 1 hour
                    time.sleep(_INACTIVE_CHECK_INTERVAL)
                    if self._is_in_active_hours():
                        break
                retry_count = 0
                continue

            connected = self._is_network_connected()
            if connected:
                retry_count = 0
                interval = self._get_interval(connected=True, success=True)
                _LOGGER.info("网络畅通，下次检查 %s 秒后", interval)
                time.sleep(interval)
                continue

            _LOGGER.info("网络未连接，尝试登录...")
            success = self._ensure_login()
            if success:
                retry_count = 0
                interval = self._get_interval(connected=False, success=True)
                _LOGGER.info("登录成功，下次检查 %s 秒后", interval)
            else:
                retry_count += 1
                interval = int(self.timed_config.get("check_interval_retry", 180))
                if retry_count >= max_retries:
                    _LOGGER.warning(
                        "登录失败次数过多 (%s/%s)，%s 秒后再检查",
                        retry_count, max_retries, interval,
                    )
                    retry_count = 0
                else:
                    _LOGGER.warning("登录失败 (%s/%s)，%s 秒后重试", retry_count, max_retries, interval)
            time.sleep(interval)

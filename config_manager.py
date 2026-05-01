"""Configuration and credential storage utilities."""

from __future__ import annotations

import json
import logging
import os
import platform
import re
from pathlib import Path
from typing import Optional

import keyring

_LOGGER = logging.getLogger(__name__)


class ConfigManager:
    def __init__(self, app_name: str = "srun_login"):
        self.app_name = app_name
        self.config_dir = self._get_config_dir()
        self.config_path = self.config_dir / "config.json"
        self.service_name = app_name
        self._ensure_dir()

    def _get_config_dir(self) -> Path:
        system = platform.system().lower()
        if system == "windows":
            base = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            return Path(base) / self.app_name
        if system == "darwin":
            return Path.home() / "Library" / "Application Support" / self.app_name
        return Path.home() / ".config" / self.app_name

    def _ensure_dir(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _default_config(self) -> dict:
        return {
            "username": "",
            "gateway": "",
            "ac_id": "1",
            "default_ip": "",
            "auto_start": False,
            "auto_connect_on_start": False,
            "start_minimized": False,
            "first_run": True,
            "suppress_startup_dialog": False,
        }

    def _safe_chmod(self) -> None:
        try:
            os.chmod(self.config_path, 0o600)
        except OSError:
            pass

    def _validate_config(self, data: dict) -> None:
        gateway = (data.get("gateway") or "").strip()
        username = (data.get("username") or "").strip()
        if not username:
            raise ValueError("用户名不能为空")
        if gateway and not re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", gateway):
            raise ValueError("网关地址格式不正确")

    def _keyring_get(self, key: str) -> Optional[str]:
        try:
            return keyring.get_password(self.service_name, key)
        except Exception:
            # 密钥链不可用时不降级为明文存储
            print("⚠️ 无法访问密钥链，请检查系统密钥服务")
            _LOGGER.exception("Keyring get failed")
            return None

    def _keyring_set(self, key: str, value: str) -> None:
        try:
            keyring.set_password(self.service_name, key, value)
        except Exception:
            print("⚠️ 无法写入密钥链，请检查系统密钥服务")
            _LOGGER.exception("Keyring set failed")

    def _keyring_delete(self, key: str) -> None:
        try:
            keyring.delete_password(self.service_name, key)
        except Exception:
            pass

    def load_config(self) -> dict:
        if not self.config_path.exists():
            return self._default_config()
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            print("⚠️ 配置文件损坏，已使用默认配置")
            _LOGGER.exception("Config load failed")
            return self._default_config()
        base = self._default_config()
        base.update(data)
        return base

    def save_config(self, data: dict) -> None:
        self._validate_config(data)
        payload = self._default_config()
        payload.update(data)
        payload.pop("password", None)
        try:
            self.config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            _LOGGER.exception("Config write failed")
            raise
        self._safe_chmod()

    def get_username(self) -> Optional[str]:
        return self._keyring_get("username")

    def get_password(self) -> Optional[str]:
        return self._keyring_get("password")

    def set_credentials(self, username: str, password: str) -> None:
        self._keyring_set("username", username)
        self._keyring_set("password", password)

    def delete_credentials(self) -> None:
        self._keyring_delete("username")
        self._keyring_delete("password")

    def set_auto_start(self, enabled: bool) -> None:
        data = self.load_config()
        data["auto_start"] = bool(enabled)
        try:
            self.save_config(data)
        except ValueError as exc:
            print(f"⚠️ 无法保存自启配置: {exc}")

    def is_auto_start_enabled(self) -> bool:
        return bool(self.load_config().get("auto_start"))

    def is_first_run(self) -> bool:
        return bool(self.load_config().get("first_run", True))

    def mark_first_run_done(self) -> None:
        data = self.load_config()
        data["first_run"] = False
        self.save_config(data)

    def reset_all(self) -> None:
        self.delete_credentials()
        if self.config_path.exists():
            try:
                self.config_path.unlink()
            except OSError:
                print("⚠️ 无法删除配置文件")

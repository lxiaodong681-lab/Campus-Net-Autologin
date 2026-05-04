"""Configuration and credential storage utilities."""

from __future__ import annotations

import base64
import getpass
import hashlib
import json
import logging
import os
import platform
import re
import uuid
from pathlib import Path
from typing import Optional

import keyring
from cryptography.fernet import Fernet

_LOGGER = logging.getLogger(__name__)


class ConfigManager:
    def __init__(self, app_name: str = "srun_login"):
        self.app_name = app_name
        self.config_dir = self._get_config_dir()
        self.config_path = self.config_dir / "config.json"
        self.credentials_path = self.config_dir / ".credentials.enc"
        self.fernet_seed_path = self.config_dir / ".credentials.seed"
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
            "timed_mode": {
                "enabled": False,
                "start_time": "07:00",
                "end_time": "23:59",
                "check_interval_connected": 600,
                "check_interval_disconnected": 120,
                "check_interval_retry": 180,
                "max_retries_per_session": 5,
            },
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

    def _get_machine_id(self) -> str:
        parts = [
            platform.node(),
            str(uuid.getnode()),
            getpass.getuser(),
        ]
        return "|".join(parts)

    def _ensure_fernet_seed(self) -> bytes:
        if self.fernet_seed_path.exists():
            return self.fernet_seed_path.read_bytes()
        seed = Fernet.generate_key()
        self.fernet_seed_path.write_bytes(seed)
        try:
            os.chmod(self.fernet_seed_path, 0o600)
        except OSError:
            pass
        return seed

    def _get_fernet(self) -> Fernet:
        seed = self._ensure_fernet_seed()
        machine_id = self._get_machine_id().encode("utf-8")
        digest = hashlib.sha256(seed + machine_id).digest()
        key = base64.urlsafe_b64encode(digest)
        return Fernet(key)

    def _read_encrypted_credentials(self) -> Optional[dict]:
        if not self.credentials_path.exists():
            return None
        try:
            payload = json.loads(self.credentials_path.read_text(encoding="utf-8"))
            token = payload.get("data")
            if not token:
                return None
            fernet = self._get_fernet()
            decrypted = fernet.decrypt(token.encode("utf-8"))
            return json.loads(decrypted.decode("utf-8"))
        except Exception as exc:
            _LOGGER.exception("Encrypted credentials read failed")
            print(f"⚠️ 加密凭据读取失败: {exc}")
            return None

    def _write_encrypted_credentials(self, username: str, password: str) -> None:
        fernet = self._get_fernet()
        data = json.dumps({"username": username, "password": password}, ensure_ascii=False)
        token = fernet.encrypt(data.encode("utf-8"))
        payload = {"data": token.decode("utf-8")}
        self.credentials_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(self.credentials_path, 0o600)
        except OSError:
            pass

    def _get_alt_keyring(self):
        try:
            import importlib

            module = importlib.import_module("keyrings.alt.file")
            EncryptedKeyring = getattr(module, "EncryptedKeyring")
        except Exception:
            return None
        try:
            kr = EncryptedKeyring()
            kr.file_path = str(self.config_dir / ".alt_keyring.cfg")
            kr.keyring_key = self._get_machine_id()
            return kr
        except Exception:
            return None

    def _keyring_get(self, key: str) -> Optional[str]:
        try:
            return keyring.get_password(self.service_name, key)
        except Exception as exc:
            # 密钥链不可用时不降级为明文存储
            print(f"❌ 密钥链读取失败: {exc}")
            print("提示：请确保系统密钥链服务已启动")
            _LOGGER.exception("Keyring get failed")
            return None

    def _keyring_set(self, key: str, value: str) -> None:
        try:
            keyring.set_password(self.service_name, key, value)
        except Exception as exc:
            print(f"❌ 密钥链写入失败: {exc}")
            print("提示：请确保系统密钥链服务已启动")
            _LOGGER.exception("Keyring set failed")
            raise RuntimeError("keyring_write_failed") from exc

    def _keyring_delete(self, key: str) -> None:
        try:
            keyring.delete_password(self.service_name, key)
        except Exception:
            pass

    def _alt_keyring_get(self, key: str) -> Optional[str]:
        alt = self._get_alt_keyring()
        if alt is None:
            return None
        try:
            return alt.get_password(self.service_name, key)
        except Exception as exc:
            _LOGGER.exception("Alt keyring get failed")
            print(f"⚠️ keyrings.alt 读取失败: {exc}")
            return None

    def _alt_keyring_set(self, key: str, value: str) -> None:
        alt = self._get_alt_keyring()
        if alt is None:
            raise RuntimeError("alt_keyring_unavailable")
        try:
            alt.set_password(self.service_name, key, value)
        except Exception as exc:
            _LOGGER.exception("Alt keyring set failed")
            raise RuntimeError("alt_keyring_write_failed") from exc

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
        # 优先从环境变量读取（最安全，完全不落盘）
        env_user = os.getenv("SRUN_USERNAME") or os.getenv("SRUN_USER")
        if env_user:
            return env_user
        value = self._keyring_get("username")
        if value:
            return value
        data = self._read_encrypted_credentials()
        if data:
            return data.get("username")
        print("⚠️ 未找到账号信息，请配置环境变量 SRUN_USERNAME")
        return None

    def get_password(self) -> Optional[str]:
        env_pass = os.getenv("SRUN_PASSWORD") or os.getenv("SRUN_PASS")
        if env_pass:
            return env_pass
        value = self._keyring_get("password")
        if value:
            return value
        data = self._read_encrypted_credentials()
        if data:
            return data.get("password")
        print("⚠️ 未找到密码信息，请配置环境变量 SRUN_PASSWORD")
        return None

    def set_credentials(self, username: str, password: str) -> None:
        try:
            self._keyring_set("username", username)
            self._keyring_set("password", password)
            return
        except Exception:
            pass
        try:
            self._alt_keyring_set("username", username)
            self._alt_keyring_set("password", password)
            return
        except Exception:
            pass
        try:
            self._write_encrypted_credentials(username, password)
            return
        except Exception as exc:
            _LOGGER.exception("Encrypted credentials write failed")
            print(f"❌ 加密凭据写入失败: {exc}")
            print("请配置环境变量 SRUN_USERNAME / SRUN_PASSWORD")
            raise RuntimeError("credential_write_failed") from exc

    def delete_credentials(self) -> None:
        self._keyring_delete("username")
        self._keyring_delete("password")
        try:
            if self.credentials_path.exists():
                self.credentials_path.unlink()
            if self.fernet_seed_path.exists():
                self.fernet_seed_path.unlink()
        except OSError:
            pass

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

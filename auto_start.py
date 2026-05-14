"""Auto-start configuration for Windows/macOS/Linux."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from environment import get_platform

_LOGGER = logging.getLogger(__name__)


class AutoStartManager:
    def __init__(self, app_name: str = "srun_login", app_path: Optional[str] = None):
        self.app_name = app_name
        self.app_path = app_path or str(Path(__file__).with_name("main.py"))

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _resolve_executable(self) -> str:
        """Return the best Python executable, preferring pythonw on Windows."""
        executable = sys.executable
        if os.name == "nt" and executable.lower().endswith("python.exe"):
            candidate = executable[:-4] + "w.exe"
            if os.path.exists(candidate):
                return candidate
        return executable

    def _build_command(self) -> str:
        exe = self._resolve_executable()
        return f'"{exe}" "{self.app_path}" --minimized'

    def _build_command_parts(self) -> list[str]:
        exe = self._resolve_executable()
        return [exe, self.app_path, "--minimized"]

    # ------------------------------------------------------------------
    # Platform-specific paths
    # ------------------------------------------------------------------

    def _windows_startup_dir(self) -> Path:
        appdata = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

    def _windows_run_key(self) -> str:
        return r"Software\Microsoft\Windows\CurrentVersion\Run"

    def _macos_plist_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / "com.srun.login.plist"

    def _linux_desktop_path(self) -> Path:
        return Path.home() / ".config" / "autostart" / "srun_login.desktop"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enable(self) -> bool:
        platform_name = get_platform()
        command = self._build_command()
        if platform_name == "windows":
            return self._enable_windows(command)
        if platform_name == "darwin":
            return self._enable_macos(command)
        return self._enable_linux(command)

    def disable(self) -> bool:
        platform_name = get_platform()
        if platform_name == "windows":
            return self._disable_windows()
        if platform_name == "darwin":
            return self._disable_macos()
        return self._disable_linux()

    def is_enabled(self) -> bool:
        platform_name = get_platform()
        if platform_name == "windows":
            return self._is_enabled_windows()
        if platform_name == "darwin":
            return self._macos_plist_path().exists()
        return self._linux_desktop_path().exists()

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------

    def _enable_windows(self, command: str) -> bool:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._windows_run_key(), 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, command)
            _LOGGER.info("Auto-start enabled via registry")
            return True
        except (ImportError, OSError) as exc:
            _LOGGER.warning("Registry auto-start failed, trying Startup folder: %s", exc)

        startup_dir = self._windows_startup_dir()
        startup_dir.mkdir(parents=True, exist_ok=True)
        batch_path = startup_dir / f"{self.app_name}.bat"
        try:
            batch_path.write_text(command + "\n", encoding="utf-8")
            _LOGGER.info("Auto-start enabled via Startup folder batch file")
            return True
        except OSError as exc:
            _LOGGER.error("Auto-start batch file write failed: %s", exc)
            return False

    def _disable_windows(self) -> bool:
        success = False
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._windows_run_key(), 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, self.app_name)
                success = True
                _LOGGER.info("Auto-start removed from registry")
        except (ImportError, OSError):
            _LOGGER.warning("Failed to remove auto-start from registry (may not exist)")

        batch_path = self._windows_startup_dir() / f"{self.app_name}.bat"
        if batch_path.exists():
            try:
                batch_path.unlink()
                success = True
                _LOGGER.info("Auto-start batch file removed")
            except OSError as exc:
                _LOGGER.warning("Failed to remove auto-start batch file: %s", exc)
        return success

    def _is_enabled_windows(self) -> bool:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._windows_run_key(), 0, winreg.KEY_READ
            ) as key:
                winreg.QueryValueEx(key, self.app_name)
                return True
        except (ImportError, OSError):
            pass
        return (self._windows_startup_dir() / f"{self.app_name}.bat").exists()

    # ------------------------------------------------------------------
    # macOS
    # ------------------------------------------------------------------

    def _enable_macos(self, command: str) -> bool:
        plist_path = self._macos_plist_path()
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        parts = self._build_command_parts()
        args_xml = "\n".join(f"        <string>{part}</string>" for part in parts)
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.srun.login</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""
        try:
            plist_path.write_text(plist_content, encoding="utf-8")
            _LOGGER.info("macOS launchd plist written")
            return True
        except OSError as exc:
            _LOGGER.error("macOS plist write failed: %s", exc)
            return False

    def _disable_macos(self) -> bool:
        plist_path = self._macos_plist_path()
        if plist_path.exists():
            try:
                plist_path.unlink()
                _LOGGER.info("macOS launchd plist removed")
                return True
            except OSError as exc:
                _LOGGER.warning("macOS plist removal failed: %s", exc)
                return False
        return True

    # ------------------------------------------------------------------
    # Linux
    # ------------------------------------------------------------------

    def _enable_linux(self, command: str) -> bool:
        desktop_path = self._linux_desktop_path()
        desktop_path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={self.app_name}\n"
            f"Exec={command}\n"
            "Hidden=false\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
        try:
            desktop_path.write_text(content, encoding="utf-8")
            _LOGGER.info("Linux .desktop autostart entry written")
            return True
        except OSError as exc:
            _LOGGER.error("Linux .desktop write failed: %s", exc)
            return False

    def _disable_linux(self) -> bool:
        desktop_path = self._linux_desktop_path()
        if desktop_path.exists():
            try:
                desktop_path.unlink()
                _LOGGER.info("Linux .desktop autostart entry removed")
                return True
            except OSError as exc:
                _LOGGER.warning("Linux .desktop removal failed: %s", exc)
                return False
        return True

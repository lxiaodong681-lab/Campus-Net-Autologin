"""运行环境检测工具"""

from __future__ import annotations

import os
import platform


def has_display() -> bool:
    """检测是否有可用显示器（用于决定是否可启动 GUI）"""
    if os.name == "nt":
        return True
    if os.name == "darwin":
        return True
    return bool(os.environ.get("DISPLAY"))


def get_platform() -> str:
    """返回当前平台：windows / darwin / linux"""
    system = platform.system().lower()
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "darwin"
    return "linux"


def is_linux_cli() -> bool:
    """是否为 Linux 纯命令行环境（无显示器）"""
    return get_platform() == "linux" and not has_display()


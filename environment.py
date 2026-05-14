"""运行环境检测工具"""

from __future__ import annotations

import os
import platform
import socket


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


def get_active_ip_addresses() -> list[str]:
    """返回本机所有非 loopback 的 IPv4 地址列表。"""
    ips: list[str] = []
    try:
        hostname = socket.gethostname()
        for (_family, _type, _proto, _canonname, sockaddr) in socket.getaddrinfo(
            hostname, None
        ):
            ip = sockaddr[0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips


def is_network_available() -> bool:
    """是否有可用的非 loopback 网络接口。

    委托给 ``network_checker`` 进行详细检测；
    若模块不可用则回退到简单 IP 检测。
    """
    try:
        from network_checker import is_network_available as _impl

        return _impl()
    except ImportError:
        return len(get_active_ip_addresses()) > 0

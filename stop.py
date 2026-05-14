"""停止校园网自动登录脚本"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import tempfile
from pathlib import Path

from config_manager import ConfigManager
from srun_login import SRUNLogin

_LOGGER = logging.getLogger(__name__)

PID_FILE = Path(tempfile.gettempdir()) / "srun_login_timed.pid"

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║         停止校园网自动登录工具                                 ║
╚══════════════════════════════════════════════════════════════╝
"""


def stop_timed_mode() -> tuple[bool, str]:
    """停止定时模式主循环（不执行 logout）"""
    if not PID_FILE.exists():
        return False, "未检测到正在运行的定时模式（PID 文件不存在）"

    try:
        pid_text = PID_FILE.read_text().strip()
        pid = int(pid_text)
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink()
        return True, f"已成功停止定时模式（PID: {pid}）"
    except ValueError:
        _LOGGER.warning("PID 文件内容损坏，已自动清理")
        if PID_FILE.exists():
            PID_FILE.unlink()
        return False, "PID 文件内容已损坏，已自动清理（定时任务可能已退出）"
    except ProcessLookupError:
        if PID_FILE.exists():
            PID_FILE.unlink()
        return False, "进程已不存在（可能已自动退出）"
    except PermissionError:
        return False, "权限不足：无法终止进程（需要更高权限）"
    except Exception as exc:
        return False, f"停止失败：{exc}"


def disconnect_and_stop() -> tuple[bool, str]:
    """断开校园网连接并停止所有任务"""
    timed_stopped = False
    if PID_FILE.exists():
        timed_success, _ = stop_timed_mode()
        timed_stopped = timed_success

    config_manager = ConfigManager()
    creds = config_manager.get_login_credentials()

    if creds is None:
        if timed_stopped:
            return True, "已停止定时模式（但未找到登录信息，无法执行断开）"
        return False, "未找到登录信息，请先配置账号"

    try:
        login = SRUNLogin(creds.username, creds.password, creds.gateway, creds.ac_id)
        logout_success = login.logout()
        if logout_success:
            return True, "已断开校园网连接并停止所有任务"
        if timed_stopped:
            return True, "已停止定时模式（但断开连接失败，可能未在线）"
        return False, "断开连接失败，可能未在线"
    except Exception as exc:
        return False, f"操作失败：{exc}"


def _interactive_menu() -> tuple[bool, str]:
    """Present an interactive menu; returns (success, message)."""
    print(BANNER)
    print("\n请选择操作：")
    print("  1. 停止定时任务（保持登录状态）")
    print("  2. 断开连接并停止所有任务（登出校园网）")
    print("  3. 返回（取消操作）\n")

    while True:
        choice = input("请输入选项（1/2/3）：").strip()
        if choice in ("1", "１"):
            success, message = stop_timed_mode()
            print("✅ " + message if success else "❌ " + message)
            return success, message
        if choice in ("2", "２"):
            success, message = disconnect_and_stop()
            print("✅ " + message if success else "❌ " + message)
            return success, message
        if choice in ("3", "３"):
            print("已取消操作")
            return True, "已取消操作"
        print("  无效选项，请重新输入 1、2 或 3")


def stop_from_gui() -> tuple[bool, str]:
    return stop_timed_mode()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--disconnect", action="store_true", help="直接断开连接并停止所有任务（不询问）")
    args = parser.parse_args()

    if args.disconnect:
        success, message = disconnect_and_stop()
    else:
        success, message = _interactive_menu()

    if success:
        print(f"✅ {message}")
        sys.exit(0)
    print(f"❌ {message}")
    sys.exit(1)

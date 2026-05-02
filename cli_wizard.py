"""交互式 CLI 配置向导（用于无 GUI 环境）"""

from __future__ import annotations

import getpass
import signal
import sys
from pathlib import Path

from config_manager import ConfigManager
from srun_login import SRUNLogin
from timed_mode import TimedLoginManager

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║         校园网自动登录工具 - 命令行模式                          ║
╚══════════════════════════════════════════════════════════════╝
"""

GITHUB_URL = "https://github.com/lxiaodong681-lab/Campus-Net-Autologin"


def _yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        answer = input(prompt + suffix).strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  请输入 y 或 n（大小写均可）")


def _input_with_default(prompt: str, default: str = "") -> str:
    if default:
        value = input(f"{prompt} [{default}]: ").strip()
        return value or default
    return input(f"{prompt}: ").strip().strip()


def _validate_time_range(value: str) -> bool:
    import re

    if not re.match(r"^\d{2}:\d{2}-\d{2}:\d{2}$", value):
        return False
    parts = value.split("-")
    for part in parts:
        hour, minute = part.split(":")
        if int(hour) > 23 or int(minute) > 59:
            return False
    return True


def _print_step(step: int, total: int, message: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  步骤 {step}/{total}: {message}")
    print(f"{'─' * 50}")


def _has_existing_config() -> bool:
    config_manager = ConfigManager()
    config = config_manager.load_config()
    username = config_manager.get_username() or config.get("username", "")
    gateway = config.get("gateway", "")
    return bool(username and gateway)


def _print_existing_config(config_manager: ConfigManager) -> None:
    config = config_manager.load_config()
    timed = config.get("timed_mode", {})
    username = config_manager.get_username() or config.get("username", "")

    print("\n检测到已有配置：")
    print(f"  网关：{config.get('gateway', '未设置')}")
    print(f"  AC_ID：{config.get('ac_id', '1')}")
    print(f"  账号：{username}")
    timed_status = "未启用"
    if timed.get("enabled"):
        timed_status = f"已启用（{timed.get('start_time', '')} 至 {timed.get('end_time', '')}）"
    print(f"  定时模式：{timed_status}")
    print()


def _clear_config(config_manager: ConfigManager) -> None:
    config_path = config_manager.config_path
    if config_path.exists():
        config_path.unlink()
    config_manager.delete_credentials()


def _collect_new_config() -> dict:
    _print_step(1, 5, "配置学校网关")
    gateway = _input_with_default("你的学校网关是", "172.17.1.2")

    _print_step(2, 5, "配置 AC_ID")
    ac_id = _input_with_default("你的学校 AC_ID 是", "1")

    _print_step(3, 5, "输入账号信息")
    username = _input_with_default("你的账号/学号是")

    _print_step(4, 5, "输入密码")
    password = getpass.getpass("你的密码是: ")

    _print_step(5, 5, "选择运行模式")
    use_timed = _yes_no("是否开启定时模式？", default=False)

    timed_config = {"enabled": False}
    if use_timed:
        while True:
            time_range = _input_with_default(
                "定时任务活跃时段（格式: HH:MM-HH:MM，例如 07:00-23:59）",
                "07:00-23:59",
            )
            if _validate_time_range(time_range):
                break
            print("  ❌ 格式错误！请使用 HH:MM-HH:MM（24小时制）")
        start_time, end_time = time_range.split("-")
        timed_config = {
            "enabled": True,
            "start_time": start_time,
            "end_time": end_time,
            "check_interval_connected": 600,
            "check_interval_disconnected": 120,
            "check_interval_retry": 180,
            "max_retries_per_session": 5,
        }

    return {
        "username": username,
        "password": password,
        "gateway": gateway,
        "ac_id": ac_id,
        "timed_mode": timed_config,
    }


def run_interactive_setup() -> None:
    print(BANNER)
    print("欢迎使用校园网自动登录工具！\n")
    print("提示：以下信息需要从学校信息中心获取，可参考 GitHub 文档：")
    print(f"  {GITHUB_URL}\n")

    config_manager = ConfigManager()

    if _has_existing_config():
        _print_existing_config(config_manager)
        answer = _yes_no("账号、密码、网关、AC_ID 已填写完毕，是否更改？", default=False)

        if answer:
            _clear_config(config_manager)
            config_data = _collect_new_config()
        else:
            config = config_manager.load_config()
            username = config_manager.get_username() or config.get("username", "")
            password = config_manager.get_password() or ""
            if not password:
                print("❌ 密码未找到（密钥链可能为空），请重新输入配置")
                _clear_config(config_manager)
                config_data = _collect_new_config()
            else:
                config_data = {
                    "username": username,
                    "password": password,
                    "gateway": config.get("gateway", ""),
                    "ac_id": config.get("ac_id", "1"),
                    "timed_mode": config.get("timed_mode", {}),
                }
    else:
        config_data = _collect_new_config()

    print("\n正在保存配置...")
    data = {
        "username": config_data["username"],
        "gateway": config_data["gateway"],
        "ac_id": config_data["ac_id"],
        "timed_mode": config_data.get("timed_mode", {}),
    }
    try:
        config_manager.save_config(data)
        config_manager.set_credentials(config_data["username"], config_data["password"])
        print("✅ 配置已保存！\n")
    except Exception as exc:
        print(f"❌ 配置保存失败: {exc}")
        sys.exit(1)

    print("正在尝试连接校园网...\n")
    login = SRUNLogin(
        config_data["username"],
        config_data["password"],
        config_data["gateway"],
        config_data["ac_id"],
    )
    success = login.login()

    if not success:
        print("❌ 登录失败，请检查账号密码是否正确，或网关地址是否匹配")
        sys.exit(1)

    print("🎉 登录成功！")
    print("\n启动信息：")
    use_timed = config_data.get("timed_mode", {}).get("enabled", False)
    print(f"  模式: {'定时模式（持续监控）' if use_timed else '常规模式（单次登录）'}")
    if use_timed:
        timed_mode = config_data["timed_mode"]
        print(f"  活跃时段: {timed_mode.get('start_time')} 至 {timed_mode.get('end_time')}")

    print("\n提示：要停止登录任务，请在另一个终端执行: python stop.py")
    print("=" * 50)

    if use_timed:
        print("\n进入定时模式主循环，按 Ctrl+C 可停止...\n")
        manager = TimedLoginManager(config_manager)

        def _sig_handler(sig, frame):
            print("\n[信息] 正在退出定时模式...")
            sys.exit(0)

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        manager.run_loop()
    else:
        print("已退出。开机后重新运行即可自动登录。")
        sys.exit(0)


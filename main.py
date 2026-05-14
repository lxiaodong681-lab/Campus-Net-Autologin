"""Main entry for the campus network auto-login tool."""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

from config_manager import ConfigManager
from environment import get_platform, has_display, is_linux_cli
from errors import ErrorCode
from shared import (
    SingleInstanceLock,
    ipc_port,
    send_ipc,
)
from srun_login import SRUNLogin


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校园网自动登录工具")
    parser.add_argument("--minimized", action="store_true", help="启动到后台")
    parser.add_argument("--background", action="store_true", help="后台静默登录并退出")
    parser.add_argument("--cli", action="store_true", help="强制使用命令行模式（不启动 GUI）")
    parser.add_argument("--timed", action="store_true", help="启动定时模式（持续监控网络，自动重连）")
    parser.add_argument("--configure", action="store_true", help="强制显示配置界面")
    parser.add_argument("--quit", action="store_true", help="退出已运行实例")
    parser.add_argument("--stop", action="store_true", help="停止正在运行的定时模式")
    parser.add_argument("--skip-preflight", action="store_true", help="跳过网络环境预检")
    return parser.parse_args()


def _run_cli_login(config_manager: ConfigManager, skip_preflight: bool = False) -> bool:
    creds = config_manager.get_login_credentials()
    if creds is None:
        print(ErrorCode.CREDENTIAL_NOT_FOUND.format())
        print("提示：请先通过图形界面配置，或手动编辑配置文件")
        return False

    if not skip_preflight:
        from network_checker import run_preflight_checks

        errors = run_preflight_checks(creds.gateway)
        for err in errors:
            print(f"❌ {err.full_message()}")

    login = SRUNLogin(
        creds.username, creds.password, creds.gateway, creds.ac_id, ip=creds.default_ip,
    )
    success = login.login()
    if success:
        print("🎉 登录成功！")
    else:
        err = login.get_last_error()
        if err:
            print(f"❌ {err.full_message()}")
        else:
            print("❌ 登录失败")
    return success


def _run_gui(config_manager: ConfigManager, options) -> None:
    from gui import run_app

    run_app(options)


def _print_platform_info(args: argparse.Namespace) -> None:
    print(
        f"[启动] 平台={get_platform()} 显示={has_display()} CLI模式={args.cli} "
        f"Linux纯CLI={is_linux_cli()}"
    )


def _setup_logging() -> None:
    logs_dir = Path(__file__).with_name("logs")
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logs_dir = Path(tempfile.gettempdir()) / "srun_login_logs"
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
    _print_platform_info(args)

    if args.stop:
        from stop import stop_timed_mode

        success, message = stop_timed_mode()
        print("✅ " + message if success else "❌ " + message)
        sys.exit(0 if success else 1)

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
        # ── Timed mode ────────────────────────────────────────────
        if args.timed:
            from timed_mode import TimedLoginManager

            manager = TimedLoginManager(config_manager)
            manager.run_loop()
            return

        # ── CLI / background ──────────────────────────────────────
        if args.background or args.cli:
            from cli_wizard import run_interactive_setup

            run_interactive_setup()
            return

        # ── Headless fallback ─────────────────────────────────────
        if not has_display():
            if args.configure:
                print("❌ 无法使用图形界面，请在有显示器的环境中配置")
                sys.exit(1)
            from cli_wizard import run_interactive_setup

            run_interactive_setup()
            return

        # ── GUI ───────────────────────────────────────────────────
        from gui import AppOptions

        data = config_manager.load_config()
        if args.configure:
            options = AppOptions(
                start_minimized=False,
                auto_connect_on_start=False,
                app_name=config_manager.app_name,
            )
        else:
            options = AppOptions(
                start_minimized=args.minimized or data.get("start_minimized", False),
                auto_connect_on_start=data.get("auto_connect_on_start", False),
                app_name=config_manager.app_name,
            )
        _run_gui(config_manager, options)
    finally:
        lock.release()


if __name__ == "__main__":
    main()

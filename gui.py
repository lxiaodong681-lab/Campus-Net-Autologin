"""GUI for campus network auto-login."""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import customtkinter

from auto_start import AutoStartManager
from config_manager import ConfigManager
from srun_login import SRUNLogin

REGULAR_MODE_INFO = (
    "【常规模式】\n\n"
    "适用场景：适合每天关机重启的个人电脑（Windows / macOS / Linux桌面）\n\n"
    "功能说明：\n"
    "- 开机时自动执行一次登录（需配合开机自启）\n"
    "- 关机重启后再次自动登录\n"
    "- 适合每天都会开关机的设备\n\n"
    "启用方式：\n"
    "- 在下方勾选\"开机自启\"即可\n"
    "- 每次开机后程序会自动在后台完成登录，无需人工干预\n\n"
    "注意：如果你使用的是长期不关机的设备（如香橙派、树莓派、服务器），\n"
    "建议使用「定时模式」，可以持续监控网络并在断线后自动重连。"
)

TIMED_MODE_INFO = (
    "【定时模式】\n\n"
    "适用场景：适合长期不关机的设备（香橙派、树莓派、服务器等）\n\n"
    "功能说明：\n"
    "- 程序会持续在后台运行，持续监控网络状态\n"
    "- 如果检测到网络断开，会自动发起登录请求\n"
    "- 每天只在指定的时段内活跃（如 07:00-23:59）\n"
    "- 在非活跃时段会进入深度休眠，不执行任何操作\n\n"
    "适用原因：\n"
    "- 校园网每天 00:00 至 07:00 关闭，07:00 后需要重新联网\n"
    "- 个人电脑关机时，定时模式帮不上忙（进程也关了）\n"
    "- 但对于长期不关机的设备，定时模式可以随时确保网络畅通\n\n"
    "频次说明：\n"
    "- 程序不会密集请求网络，而是模拟人类行为\n"
    "- 检查间隔为 5-15 分钟（可在设置中自定义）\n"
    "- 不会对校园网服务器造成压力\n\n"
    "时段配置：\n"
    "- 设置一个每天重复的活跃时段（如 07:00-23:59）\n"
    "- 程序只在该时段内监控网络\n"
    "- 时段结束后程序进入休眠，直到第二天时段开始"
)


def _ipc_port(app_name: str) -> int:
    import hashlib

    digest = hashlib.md5(app_name.encode("utf-8")).hexdigest()
    return 38000 + (int(digest[:6], 16) % 1000)


@dataclass
class AppOptions:
    start_minimized: bool = False
    auto_connect_on_start: bool = False
    app_name: str = "srun_login"


class SrunApp(customtkinter.CTk):
    def __init__(self, config: ConfigManager, auto_start: AutoStartManager, options: AppOptions):
        super().__init__()
        self.config_manager = config
        self.auto_start_manager = auto_start
        self.options = options
        self.title("校园网自动连接工具")
        self.geometry("400x580")
        self.minsize(400, 580)
        customtkinter.set_appearance_mode("System")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.status_icon = customtkinter.StringVar(value="🔴")
        self.status_text = customtkinter.StringVar(value="未连接")
        self.username_var = customtkinter.StringVar()
        self.password_var = customtkinter.StringVar()
        self.gateway_var = customtkinter.StringVar(value="")
        self.ac_id_var = customtkinter.StringVar(value="1")
        self.auto_start_var = customtkinter.BooleanVar(value=False)
        self.auto_connect_var = customtkinter.BooleanVar(value=False)
        self.minimize_var = customtkinter.BooleanVar(value=False)
        self.timed_mode_var = customtkinter.BooleanVar(value=False)
        self.timed_start_var = customtkinter.StringVar(value="07:00")
        self.timed_end_var = customtkinter.StringVar(value="23:59")

        self._build_ui()
        self._load_config()
        self._ipc_stop_event = threading.Event()
        self._start_ipc_listener()
        self.after(100, self._maybe_show_startup_dialog)

        if self.options.auto_connect_on_start:
            self._append_log("🐾 启动时自动连接")
            self.after(300, self._on_connect)
        if self.options.start_minimized:
            self.after(100, self.withdraw)

    def _build_ui(self) -> None:
        status_frame = customtkinter.CTkFrame(self)
        status_frame.pack(fill="x", padx=20, pady=8)
        customtkinter.CTkLabel(status_frame, textvariable=self.status_icon, font=("Arial", 32)).pack(pady=5)
        customtkinter.CTkLabel(status_frame, textvariable=self.status_text).pack(pady=5)

        form_frame = customtkinter.CTkFrame(self)
        form_frame.pack(fill="x", padx=20, pady=4)
        self._form_row(form_frame, "账号：", self.username_var)
        self._form_row(form_frame, "密码：", self.password_var, show="*")
        self._form_row(form_frame, "网关：", self.gateway_var, placeholder="请输入学校网关地址")
        self._form_row(form_frame, "AC_ID：", self.ac_id_var)

        options_frame = customtkinter.CTkFrame(self)
        options_frame.pack(fill="x", padx=20, pady=4)
        customtkinter.CTkCheckBox(options_frame, text="开机自动启动", variable=self.auto_start_var,
                                  command=self._on_toggle_autostart).pack(anchor="w", pady=2)
        customtkinter.CTkCheckBox(options_frame, text="启动时自动连接", variable=self.auto_connect_var).pack(
            anchor="w", pady=2
        )
        customtkinter.CTkCheckBox(options_frame, text="连接成功后最小化", variable=self.minimize_var).pack(
            anchor="w", pady=2
        )

        mode_frame = customtkinter.CTkFrame(self)
        mode_frame.pack(fill="x", padx=20, pady=4)
        mode_header = customtkinter.CTkFrame(mode_frame)
        mode_header.pack(fill="x", pady=2)
        customtkinter.CTkLabel(mode_header, text="常规模式").pack(side="left")
        customtkinter.CTkButton(
            mode_header,
            text="详情",
            width=60,
            command=lambda: self._show_mode_info_dialog("regular"),
        ).pack(side="right")

        hint_label = customtkinter.CTkLabel(
            mode_frame,
            text="定时模式与常规模式相互独立，可同时启用",
            text_color=("gray50"),
            font=("", 10),
        )
        hint_label.pack(fill="x", pady=2)

        timed_header = customtkinter.CTkFrame(mode_frame)
        timed_header.pack(fill="x", pady=4)
        customtkinter.CTkCheckBox(
            timed_header,
            text="启用定时模式",
            variable=self.timed_mode_var,
            command=self._on_toggle_timed_mode,
        ).pack(side="left")
        customtkinter.CTkButton(
            timed_header,
            text="详情",
            width=60,
            command=lambda: self._show_mode_info_dialog("timed"),
        ).pack(side="right")

        timed_config = customtkinter.CTkFrame(mode_frame)
        timed_config.pack(fill="x", pady=2)
        customtkinter.CTkLabel(timed_config, text="活跃时段").pack(side="left")
        customtkinter.CTkEntry(timed_config, textvariable=self.timed_start_var, width=70).pack(side="left", padx=4)
        customtkinter.CTkLabel(timed_config, text="至").pack(side="left")
        customtkinter.CTkEntry(timed_config, textvariable=self.timed_end_var, width=70).pack(side="left", padx=4)

        button_frame = customtkinter.CTkFrame(self)
        button_frame.pack(fill="x", padx=20, pady=4)
        customtkinter.CTkButton(button_frame, text="保存配置", command=self._on_save).pack(side="left", padx=5)
        self.stop_timed_button = customtkinter.CTkButton(
            button_frame,
            text="停止定时",
            command=self._on_stop_timed,
            fg_color="transparent",
            text_color=("orange", "orange"),
        )
        self.stop_timed_button.pack(side="left", padx=2)
        self.stop_timed_button.bind(
            "<Enter>",
            lambda _event: self._show_tooltip("停止定时监控任务，但保持已登录状态"),
        )
        self.stop_timed_button.bind("<Leave>", lambda _event: self._hide_tooltip())
        self.disconnect_button = customtkinter.CTkButton(
            button_frame,
            text="断开连接",
            command=self._on_disconnect,
            fg_color="transparent",
            text_color=("red", "red"),
        )
        self.disconnect_button.pack(side="left", padx=2)
        self.disconnect_button.bind(
            "<Enter>",
            lambda _event: self._show_tooltip("断开校园网连接并停止所有任务"),
        )
        self.disconnect_button.bind("<Leave>", lambda _event: self._hide_tooltip())
        customtkinter.CTkButton(button_frame, text="立即连接", command=self._on_connect).pack(side="right", padx=5)

        log_frame = customtkinter.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=20, pady=8)
        self.log_text = customtkinter.CTkTextbox(log_frame, height=200)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

    def _form_row(self, parent, label: str, variable, show: Optional[str] = None, placeholder: str = "") -> None:
        row = customtkinter.CTkFrame(parent)
        row.pack(fill="x", pady=2)
        customtkinter.CTkLabel(row, text=label, width=80, anchor="w").pack(side="left")
        entry = customtkinter.CTkEntry(row, textvariable=variable, show=show or "", placeholder_text=placeholder)
        entry.pack(side="left", fill="x", expand=True)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        print(message)

    def _load_config(self) -> None:
        data = self.config_manager.load_config()
        timed_config = data.get("timed_mode", {})
        stored_username = self.config_manager.get_username() or data.get("username", "")
        self.username_var.set(stored_username)
        self.password_var.set(self.config_manager.get_password() or "")
        gateway_value = data.get("gateway") or "172.17.1.2"
        self.gateway_var.set(gateway_value)
        self.ac_id_var.set(data.get("ac_id") or "1")
        self.auto_start_var.set(bool(data.get("auto_start")))
        self.auto_connect_var.set(bool(data.get("auto_connect_on_start")))
        self.minimize_var.set(bool(data.get("start_minimized")))
        self.timed_mode_var.set(bool(timed_config.get("enabled", False)))
        self.timed_start_var.set(timed_config.get("start_time", "07:00"))
        self.timed_end_var.set(timed_config.get("end_time", "23:59"))

    def _maybe_show_startup_dialog(self) -> None:
        config = self.config_manager.load_config()
        if config.get("suppress_startup_dialog"):
            return

        self.withdraw()
        dialog = customtkinter.CTkToplevel(self)
        dialog.title("使用说明")
        dialog.geometry("420x220")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.focus_set()

        message = (
            "警告：默认网关（172.17.1.2）为江西师范大学示例值，"
            "其他学校用户请务必更改为本校实际网关地址！"
            "网关和 AC_ID 因每个学校的环境而异，如果默认值无法连接，"
            "请参考学校官网或使用抓包工具获取。"
        )
        content = customtkinter.CTkLabel(dialog, text=message, wraplength=380, justify="left")
        content.pack(padx=20, pady=20, fill="x")

        footer = customtkinter.CTkFrame(dialog)
        footer.pack(fill="x", padx=10, pady=10)
        suppress_var = customtkinter.BooleanVar(value=False)
        suppress_box = customtkinter.CTkCheckBox(footer, text="不再提示", variable=suppress_var)
        suppress_box.pack(side="left")

        def close_dialog() -> None:
            if suppress_var.get():
                updated = self.config_manager.load_config()
                updated["suppress_startup_dialog"] = True
                try:
                    self.config_manager.save_config(updated)
                except Exception as exc:
                    self._append_log(f"⚠️ 无法保存提示设置: {exc}")
            dialog.destroy()

        customtkinter.CTkButton(footer, text="知道了", command=close_dialog).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.wait_window()
        self.deiconify()

    def _show_mode_info_dialog(self, mode: str) -> None:
        dialog = customtkinter.CTkToplevel(self)
        dialog.title("常规模式 详情" if mode == "regular" else "定时模式 详情")
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()

        content = REGULAR_MODE_INFO if mode == "regular" else TIMED_MODE_INFO
        label = customtkinter.CTkLabel(dialog, text=content, wraplength=450, justify="left")
        label.pack(padx=20, pady=20)
        customtkinter.CTkButton(dialog, text="我知道了", command=dialog.destroy).pack(pady=10)
        dialog.wait_window()

    def _on_toggle_timed_mode(self) -> None:
        if self.timed_mode_var.get():
            self._show_mode_info_dialog("timed")

    def _on_toggle_autostart(self) -> None:
        enabled = self.auto_start_var.get()
        if enabled:
            if self.auto_start_manager.enable():
                self._append_log("✨ 开机自启已启用")
                self.config_manager.set_auto_start(True)
            else:
                self.auto_start_var.set(False)
                self._append_log("❌ 开机自启启用失败")
        else:
            if self.auto_start_manager.disable():
                self._append_log("✨ 开机自启已关闭")
                self.config_manager.set_auto_start(False)
            else:
                self.auto_start_var.set(True)
                self._append_log("❌ 开机自启关闭失败")

    def _on_save(self) -> None:
        existing = self.config_manager.load_config()
        timed_config = existing.get("timed_mode", {}).copy()
        timed_config.update(
            {
                "enabled": self.timed_mode_var.get(),
                "start_time": self.timed_start_var.get().strip() or "07:00",
                "end_time": self.timed_end_var.get().strip() or "23:59",
            }
        )
        data = {
            "username": self.username_var.get().strip(),
            "gateway": self.gateway_var.get().strip(),
            "ac_id": self.ac_id_var.get().strip() or "1",
            "auto_start": self.auto_start_var.get(),
            "auto_connect_on_start": self.auto_connect_var.get(),
            "start_minimized": self.minimize_var.get(),
            "timed_mode": timed_config,
        }
        try:
            self.config_manager.save_config(data)
            self.config_manager.set_credentials(data["username"], self.password_var.get())
            self._append_log("✨ 配置已保存")
        except Exception as exc:
            self._append_log(f"❌ 保存失败: {exc}")

    def _on_connect(self) -> None:
        self._set_status("🟡", "连接中")
        worker = threading.Thread(target=self._do_login, daemon=True)
        worker.start()

    def _do_login(self) -> None:
        username = self.username_var.get().strip()
        password = self.password_var.get()
        gateway = self.gateway_var.get().strip()
        ac_id = self.ac_id_var.get().strip() or "1"
        default_ip = self.config_manager.load_config().get("default_ip") or None
        if not username or not password or not gateway:
            self.after(0, lambda: self._append_log("❌ 请填写账号、密码和网关"))
            self.after(0, lambda: self._set_status("🔴", "未连接"))
            return
        login = SRUNLogin(username, password, gateway, ac_id, ip=default_ip)
        success = login.login()
        if success:
            self.after(0, lambda: self._set_status("🟢", "已连接"))
            if self.minimize_var.get():
                self.after(300, self.withdraw)
        else:
            self.after(0, lambda: self._set_status("🔴", "未连接"))

    def _set_status(self, icon: str, text: str) -> None:
        self.status_icon.set(icon)
        self.status_text.set(text)

    def _on_close(self) -> None:
        self.withdraw()
        self._append_log("⚠️ 已最小化到后台")
        return

    def _quit_app(self) -> None:
        self._ipc_stop_event.set()
        self.destroy()

    def show_window(self) -> None:
        self.deiconify()
        self.lift()

    def _start_ipc_listener(self) -> None:
        port = _ipc_port(self.options.app_name)

        def loop() -> None:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    server.bind(("127.0.0.1", port))
                except OSError:
                    return
                server.listen(1)
                server.settimeout(0.5)
                while not self._ipc_stop_event.is_set():
                    try:
                        conn, _ = server.accept()
                    except socket.timeout:
                        continue
                    with conn:
                        data = conn.recv(32).decode("utf-8", errors="ignore").strip()
                        if data == "show":
                            self.after(0, self.show_window)
                        elif data == "quit":
                            self.after(0, self._quit_app)
                    time.sleep(0.1)

        threading.Thread(target=loop, daemon=True).start()

    def _on_stop_timed(self) -> None:
        def _do_stop():
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("stop.py"))],
                capture_output=True,
                text=True,
            )
            success = result.returncode == 0
            message = (result.stdout + result.stderr).strip()
            self.after(0, lambda: self._show_stop_result_dialog(success, message, is_disconnect=False))

        threading.Thread(target=_do_stop, daemon=True).start()

    def _on_disconnect(self) -> None:
        def _do_disconnect():
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("stop.py")), "--disconnect"],
                capture_output=True,
                text=True,
            )
            success = result.returncode == 0
            message = (result.stdout + result.stderr).strip()
            self.after(0, lambda: self._show_stop_result_dialog(success, message, is_disconnect=True))

        threading.Thread(target=_do_disconnect, daemon=True).start()

    def _show_tooltip(self, text: str) -> None:
        if not hasattr(self, "tooltip_label"):
            self.tooltip_label = customtkinter.CTkLabel(
                self,
                text="",
                bg_color="#333333",
                text_color="white",
                corner_radius=5,
            )
        self.tooltip_label.configure(text=text)
        self.tooltip_label.place(relx=0.5, rely=0.95, anchor="center")
        self.tooltip_label.lift()

    def _hide_tooltip(self) -> None:
        if hasattr(self, "tooltip_label"):
            self.tooltip_label.place_forget()

    def _show_stop_result_dialog(self, success: bool, message: str, is_disconnect: bool) -> None:
        dialog = customtkinter.CTkToplevel(self)
        dialog.title("停止结果")
        dialog.geometry("350x150")
        dialog.transient(self)
        dialog.grab_set()

        icon = "✅" if success else "❌"
        customtkinter.CTkLabel(dialog, text=icon, font=("Arial", 40)).pack(pady=10)

        if is_disconnect:
            content_text = "已断开校园网连接并停止所有任务" if success else (message or "断开连接失败")
        else:
            content_text = "已停止定时监控任务（保持登录状态）" if success else (message or "停止定时任务失败")

        customtkinter.CTkLabel(dialog, text=content_text, wraplength=300).pack(pady=5)
        customtkinter.CTkButton(dialog, text="确定", command=dialog.destroy).pack(pady=10)

        if success:
            self._set_status("🔴", "未连接")
            self._append_log("⚠️ " + ("已停止定时" if not is_disconnect else "已断开连接并停止所有任务"))


def run_app(options: Optional[AppOptions] = None) -> None:
    config = ConfigManager()
    auto_start = AutoStartManager(app_path=str(__file__).replace("gui.py", "main.py"))
    app = SrunApp(config, auto_start, options or AppOptions())
    app.mainloop()

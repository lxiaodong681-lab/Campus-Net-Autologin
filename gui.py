"""GUI for campus network auto-login."""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from typing import Optional

import customtkinter

from auto_start import AutoStartManager
from config_manager import ConfigManager
from srun_login import SRUNLogin


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
        self.geometry("400x520")
        self.minsize(380, 520)
        customtkinter.set_appearance_mode("System")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.status_icon = customtkinter.StringVar(value="🔴")
        self.status_text = customtkinter.StringVar(value="未连接")
        self.username_var = customtkinter.StringVar()
        self.password_var = customtkinter.StringVar()
        self.gateway_var = customtkinter.StringVar(value="172.17.1.2")
        self.ac_id_var = customtkinter.StringVar(value="1")
        self.auto_start_var = customtkinter.BooleanVar(value=False)
        self.auto_connect_var = customtkinter.BooleanVar(value=False)
        self.minimize_var = customtkinter.BooleanVar(value=False)

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
        status_frame.pack(fill="x", padx=20, pady=10)
        customtkinter.CTkLabel(status_frame, textvariable=self.status_icon, font=("Arial", 32)).pack(pady=5)
        customtkinter.CTkLabel(status_frame, textvariable=self.status_text).pack(pady=5)

        form_frame = customtkinter.CTkFrame(self)
        form_frame.pack(fill="x", padx=20, pady=5)
        self._form_row(form_frame, "账号：", self.username_var)
        self._form_row(form_frame, "密码：", self.password_var, show="*")
        self._form_row(form_frame, "网关：", self.gateway_var)
        self._form_row(form_frame, "AC_ID：", self.ac_id_var)

        options_frame = customtkinter.CTkFrame(self)
        options_frame.pack(fill="x", padx=20, pady=5)
        customtkinter.CTkCheckBox(options_frame, text="开机自动启动", variable=self.auto_start_var,
                                  command=self._on_toggle_autostart).pack(anchor="w", pady=2)
        customtkinter.CTkCheckBox(options_frame, text="启动时自动连接", variable=self.auto_connect_var).pack(
            anchor="w", pady=2
        )
        customtkinter.CTkCheckBox(options_frame, text="连接成功后最小化", variable=self.minimize_var).pack(
            anchor="w", pady=2
        )

        button_frame = customtkinter.CTkFrame(self)
        button_frame.pack(fill="x", padx=20, pady=5)
        customtkinter.CTkButton(button_frame, text="保存配置", command=self._on_save).pack(side="left", padx=5)
        customtkinter.CTkButton(button_frame, text="立即连接", command=self._on_connect).pack(side="right", padx=5)

        log_frame = customtkinter.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=20, pady=10)
        self.log_text = customtkinter.CTkTextbox(log_frame, height=180)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

    def _form_row(self, parent, label: str, variable, show: Optional[str] = None) -> None:
        row = customtkinter.CTkFrame(parent)
        row.pack(fill="x", pady=2)
        customtkinter.CTkLabel(row, text=label, width=80, anchor="w").pack(side="left")
        entry = customtkinter.CTkEntry(row, textvariable=variable, show=show or "")
        entry.pack(side="left", fill="x", expand=True)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        print(message)

    def _load_config(self) -> None:
        data = self.config_manager.load_config()
        stored_username = self.config_manager.get_username() or data.get("username", "")
        self.username_var.set(stored_username)
        self.password_var.set(self.config_manager.get_password() or "")
        self.gateway_var.set(data.get("gateway") or "172.17.1.2")
        self.ac_id_var.set(data.get("ac_id") or "1")
        self.auto_start_var.set(bool(data.get("auto_start")))
        self.auto_connect_var.set(bool(data.get("auto_connect_on_start")))
        self.minimize_var.set(bool(data.get("start_minimized")))

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
            "注意：网关和 AC_ID 因每个学校的环境而异。"
            "如果默认值无法连接，请参考学校官网或手动抓包获取。"
            "当前默认预设为【江西师范大学】的配置信息。"
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
        data = {
            "username": self.username_var.get().strip(),
            "gateway": self.gateway_var.get().strip(),
            "ac_id": self.ac_id_var.get().strip() or "1",
            "auto_start": self.auto_start_var.get(),
            "auto_connect_on_start": self.auto_connect_var.get(),
            "start_minimized": self.minimize_var.get(),
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


def run_app(options: Optional[AppOptions] = None) -> None:
    config = ConfigManager()
    auto_start = AutoStartManager(app_path=str(__file__).replace("gui.py", "main.py"))
    app = SrunApp(config, auto_start, options or AppOptions())
    app.mainloop()

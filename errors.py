"""Structured error codes with user-facing messages and suggestions."""

from __future__ import annotations

from enum import Enum


class ErrorCode(Enum):
    # ── Network layer (1xxx) ──────────────────────────────────────────
    NO_NETWORK_INTERFACE = (
        1001,
        "没有找到校园网，请检查设备是否正常（无线网卡/有线网卡是否已启用）",
    )
    GATEWAY_UNREACHABLE = (
        1002,
        "无法连接到校园网网关 {gateway}，请检查网线是否插好或 WiFi 是否已连接",
    )
    DNS_RESOLUTION_FAILED = (
        1003,
        "DNS 解析失败，请检查网络连接或 DNS 设置",
    )
    NETWORK_TIMEOUT = (
        1004,
        "网络请求超时，请检查校园网是否可达",
    )
    BAIDU_UNREACHABLE = (
        1005,
        "无法访问互联网（百度检测失败），可能未登录校园网或网络中断",
    )

    # ── Authentication layer (2xxx) ───────────────────────────────────
    WRONG_CREDENTIALS = (2001, "账号或密码错误，请检查后重试")
    ACCOUNT_NOT_EXIST = (2002, "账号不存在，请确认学号/工号是否正确")
    ACCOUNT_DISABLED = (2003, "账号已被禁用，请联系学校信息中心")
    ALREADY_ONLINE = (2004, "账号已在其他设备登录，请先下线后再试")
    AUTH_TIMEOUT = (2005, "认证超时，请稍后重试或检查网关地址是否正确")
    NETWORK_ANOMALY = (2006, "校园网网络异常，请稍后重试")
    IP_ALREADY_ONLINE = (2007, "当前 IP 已在线，请先断开已有连接")
    LOGIN_RESPONSE_UNKNOWN = (2008, "登录响应异常，服务器返回了未知错误")
    CHALLENGE_FAILED = (2009, "获取认证挑战码失败，网关可能不支持该认证方式")

    # ── Configuration layer (3xxx) ────────────────────────────────────
    CONFIG_MISSING = (3001, "缺少必要配置（{missing}），请先完成配置")
    CONFIG_CORRUPTED = (3002, "配置文件已损坏，将使用默认配置")
    GATEWAY_FORMAT_INVALID = (3003, "网关地址格式不正确，请输入有效的 IPv4 地址")
    CREDENTIAL_NOT_FOUND = (3004, "未找到登录凭据，请配置环境变量或运行配置向导")
    KEYRING_UNAVAILABLE = (3005, "系统密钥链不可用，请确保密钥链服务已启动")

    # ── System layer (4xxx) ───────────────────────────────────────────
    AUTO_START_FAILED = (4001, "开机自启设置失败，请检查系统权限")
    PID_FILE_STALE = (4002, "检测到残留的定时任务 PID 文件，已自动清理")
    PERMISSION_DENIED = (4003, "权限不足，请以管理员/root 身份运行")

    # ── Instance management (5xxx) ────────────────────────────────────
    INSTANCE_ALREADY_RUNNING = (5001, "程序已在运行中，已切换到已有窗口")

    # ── General / unknown ─────────────────────────────────────────────
    UNKNOWN_ERROR = (9999, "发生未知错误: {detail}")

    # ------------------------------------------------------------------

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message

    def format(self, **kwargs: str) -> str:
        """Return the message with placeholders replaced."""
        return self.message.format(**kwargs)

    def full_message(self, **kwargs: str) -> str:
        """Return '[E{code}] formatted message'."""
        return f"[E{self.code}] {self.format(**kwargs)}"

    @classmethod
    def from_code(cls, code: int) -> ErrorCode:
        for member in cls:
            if member.code == code:
                return member
        return cls.UNKNOWN_ERROR

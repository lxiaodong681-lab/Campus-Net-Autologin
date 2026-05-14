"""Core Srun login client."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import socket
import time
from typing import Callable, Optional

import requests

from errors import ErrorCode

_BASE64_CHARS = "LVoJPiCN2R8G90yg+hmFHuacZ1OWMnrsSTXkYpUq/3dlbfKwv6xztjI7DeBE45QA"
_LOGGER = logging.getLogger(__name__)

_REQUEST_DELAY = 0.5       # seconds between HTTP requests to avoid rate-limiting
_RETRY_DELAY = 0.3         # seconds after a failed HTTP call
_CHALLENGE_DELAY = 0.8     # seconds between IP detection and challenge fetch


def _str_to_uints(data: str, include_length: bool) -> list[int]:
    raw = data.encode("utf-8")
    length = len(raw)
    n = (length + 3) // 4
    result: list[int] = []
    for i in range(n):
        chunk = raw[i * 4 : i * 4 + 4]
        value = int.from_bytes(chunk.ljust(4, b"\0"), "little")
        result.append(value)
    if include_length:
        result.append(length)
    return result


def _uints_to_bytes(values: list[int], include_length: bool) -> bytes:
    if include_length:
        length = values[-1]
        values = values[:-1]
    else:
        length = len(values) * 4
    raw = b"".join((v & 0xFFFFFFFF).to_bytes(4, "little") for v in values)
    return raw[:length]


def xencode(msg: str, key: str) -> bytes:
    if not msg:
        return b""
    v = _str_to_uints(msg, True)
    k = _str_to_uints(key, False)
    if len(k) < 4:
        k.extend([0] * (4 - len(k)))
    n = len(v) - 1
    z = v[n]
    y = v[0]
    delta = 0x9E3779B9
    total = 0
    q = 6 + 52 // (n + 1)
    while q > 0:
        total = (total + delta) & 0xFFFFFFFF
        e = (total >> 2) & 3
        for p in range(n):
            y = v[p + 1]
            mx = (
                ((z >> 5) ^ (y << 2))
                + ((y >> 3) ^ (z << 4))
                ^ ((total ^ y) + (k[(p & 3) ^ e] ^ z))
            )
            v[p] = (v[p] + mx) & 0xFFFFFFFF
            z = v[p]
        y = v[0]
        mx = (
            ((z >> 5) ^ (y << 2))
            + ((y >> 3) ^ (z << 4))
            ^ ((total ^ y) + (k[(n & 3) ^ e] ^ z))
        )
        v[n] = (v[n] + mx) & 0xFFFFFFFF
        z = v[n]
        q -= 1
    return _uints_to_bytes(v, False)


def get_base64(data: bytes) -> str:
    result: list[str] = []
    i = 0
    while i < len(data):
        b1 = data[i]
        b2 = data[i + 1] if i + 1 < len(data) else None
        b3 = data[i + 2] if i + 2 < len(data) else None
        if b2 is None:
            result.append(_BASE64_CHARS[b1 >> 2])
            result.append(_BASE64_CHARS[(b1 & 0x03) << 4])
            result.append("=")
            result.append("=")
        elif b3 is None:
            result.append(_BASE64_CHARS[b1 >> 2])
            result.append(_BASE64_CHARS[((b1 & 0x03) << 4) | (b2 >> 4)])
            result.append(_BASE64_CHARS[(b2 & 0x0F) << 2])
            result.append("=")
        else:
            result.append(_BASE64_CHARS[b1 >> 2])
            result.append(_BASE64_CHARS[((b1 & 0x03) << 4) | (b2 >> 4)])
            result.append(_BASE64_CHARS[((b2 & 0x0F) << 2) | (b3 >> 6)])
            result.append(_BASE64_CHARS[b3 & 0x3F])
        i += 3
    return "".join(result)


def get_md5(password: str, token: str) -> str:
    digest = hmac.new(token.encode("utf-8"), b"", hashlib.md5).hexdigest()
    return f"{{MD5}}{digest}"


def get_sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


# ── Error-code mapping from Srun server responses ───────────────────────

_SRUN_ERROR_MAP: dict[str, ErrorCode] = {
    "E3001": ErrorCode.WRONG_CREDENTIALS,
    "E3002": ErrorCode.ACCOUNT_NOT_EXIST,
    "E3006": ErrorCode.NETWORK_ANOMALY,
    "E2531": ErrorCode.IP_ALREADY_ONLINE,
    "E2553": ErrorCode.ACCOUNT_DISABLED,
    "E2616": ErrorCode.ALREADY_ONLINE,
    "E2620": ErrorCode.AUTH_TIMEOUT,
}


class SRUNLogin:
    def __init__(
        self,
        username: str,
        password: str,
        gateway: str,
        ac_id: str,
        ip: str | None = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.username = username
        self.password = password
        self.gateway = gateway
        self.ac_id = ac_id
        self.ip = ip
        self.session = requests.Session()
        self.timeout = 5
        self.last_error: Optional[ErrorCode] = None
        self._log_cb = log_callback

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, prefix: str, message: str) -> None:
        if self._log_cb is not None:
            self._log_cb(prefix, message)
        else:
            print(f"{prefix} {message}")
        if prefix in {"❌", "⚠️"}:
            _LOGGER.warning(message)
        else:
            _LOGGER.info(message)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _callback(self, ts: int) -> str:
        return f"jQuery{ts}_{ts}"

    def _get(self, url: str, params: Optional[dict] = None) -> Optional[str]:
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.text
        except requests.Timeout:
            self._log("❌", "网络请求超时，请检查校园网是否可达")
            self.last_error = ErrorCode.NETWORK_TIMEOUT
            _LOGGER.exception("HTTP GET timeout")
            return None
        except requests.ConnectionError:
            self._log("❌", f"无法连接到 {self.gateway}，请检查网络")
            self.last_error = ErrorCode.GATEWAY_UNREACHABLE
            _LOGGER.exception("HTTP GET connection error")
            return None
        except requests.RequestException as exc:
            time.sleep(_RETRY_DELAY)
            self._log("❌", f"网络请求失败: {exc}")
            _LOGGER.exception("HTTP GET failed")
            return None

    def _post(self, url: str, data: dict) -> Optional[str]:
        try:
            resp = self.session.post(url, data=data, timeout=self.timeout)
            resp.raise_for_status()
            return resp.text
        except requests.Timeout:
            self._log("❌", "网络请求超时，请检查校园网是否可达")
            self.last_error = ErrorCode.NETWORK_TIMEOUT
            _LOGGER.exception("HTTP POST timeout")
            return None
        except requests.ConnectionError:
            self._log("❌", f"无法连接到 {self.gateway}，请检查网络")
            self.last_error = ErrorCode.GATEWAY_UNREACHABLE
            _LOGGER.exception("HTTP POST connection error")
            return None
        except requests.RequestException as exc:
            time.sleep(_RETRY_DELAY)
            self._log("❌", f"网络请求失败: {exc}")
            _LOGGER.exception("HTTP POST failed")
            return None

    # ------------------------------------------------------------------
    # Gateway reachability
    # ------------------------------------------------------------------

    def _check_gateway_reachable(self) -> bool:
        """Quick TCP-connect to gateway:80 to verify basic reachability."""
        try:
            with socket.create_connection((self.gateway, 80), timeout=3.0):
                pass
            return True
        except OSError:
            self._log("❌", f"网关 {self.gateway} 不可达，请检查网络连接")
            self.last_error = ErrorCode.GATEWAY_UNREACHABLE
            return False

    # ------------------------------------------------------------------
    # JSON helpers
    # ------------------------------------------------------------------

    def _extract_json(self, text: str) -> Optional[dict]:
        if not isinstance(text, str):
            _LOGGER.warning("_extract_json called with non-string: %s", type(text))
            return None
        match = re.search(r"\((\{.*\})\)", text, re.S)
        payload = match.group(1) if match else text
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.exception("Failed to parse JSON response")
            return None

    # ------------------------------------------------------------------
    # Login flow
    # ------------------------------------------------------------------

    def _get_login_page_ip(self) -> Optional[str]:
        url = f"http://{self.gateway}/srun_portal_pc"
        params = {"ac_id": self.ac_id, "theme": "pro"}
        self._log("🐾", "获取登录页面以检测本机 IP")
        resp = self._get(url, params=params)
        if not resp:
            return None
        match = re.search(r'id="user_ip" value="(.*?)"', resp)
        if match:
            self._log("📍", f"检测到 IP: {match.group(1)}")
            return match.group(1)
        self._log("⚠️", "未能从登录页解析 IP")
        return None

    def get_challenge(self) -> Optional[str]:
        ts = int(time.time() * 1000)
        callback = self._callback(ts)
        params = {
            "callback": callback,
            "username": self.username,
            "ip": self.ip or "",
            "_": ts,
        }
        url = f"http://{self.gateway}/cgi-bin/get_challenge"
        self._log("🐾", "获取 challenge token")
        resp = self._get(url, params=params)
        if not resp:
            return None
        data = self._extract_json(resp)
        token = data.get("challenge") if data else None
        if token:
            self._log("✨", "成功获取 challenge token")
            return token
        self._log("❌", f"获取 challenge 失败: {resp}")
        self.last_error = ErrorCode.CHALLENGE_FAILED
        return None

    def _encode_info(self, token: str, ip: str) -> str:
        # The plain-text password is temporarily in memory here --
        # it is encrypted before being sent over the wire.
        info_dict = {
            "username": self.username,
            "password": self.password,
            "ip": ip,
            "acid": self.ac_id,
            "enc_ver": "srun_bx1",
        }
        info_str = json.dumps(info_dict, separators=(",", ":"), ensure_ascii=False)
        encrypted = xencode(info_str, token)
        return "{SRBX1}" + get_base64(encrypted)

    def _is_login_success(self, text: str) -> bool:
        """Check the response for a definitive success indicator.

        Matches ``login_ok``, ``"error":"ok"``, or the JSON field
        ``error == "ok"``.  The previous ``"suc" in text`` heuristic
        has been removed because it produced false positives
        (e.g. matching the word "success" in unrelated content).
        """
        if "login_ok" in text or '"error":"ok"' in text:
            return True
        data = self._extract_json(text)
        if data and data.get("error") == "ok":
            return True
        return False

    def login(self) -> bool:
        self.last_error = None

        # --- pre-flight: gateway reachable? ---
        if not self._check_gateway_reachable():
            return False

        ip_from_page = self._get_login_page_ip()
        if ip_from_page:
            self.ip = ip_from_page
        if not self.ip:
            self._log("❌", "无法确定本机 IP")
            self.last_error = self.last_error or ErrorCode.NETWORK_ANOMALY
            return False

        time.sleep(_CHALLENGE_DELAY)
        token = self.get_challenge()
        if not token:
            return False

        info = self._encode_info(token, self.ip)
        md5 = get_md5(self.password, token)
        chk_input = (
            token + self.username
            + token + md5
            + token + self.ac_id
            + token + self.ip
            + token + "200"
            + token + "1"
            + token + info
        )
        chksum = get_sha1(chk_input)

        ts = int(time.time() * 1000)
        callback = self._callback(ts)
        payload = {
            "callback": callback,
            "action": "login",
            "username": self.username,
            "password": md5,
            "ac_id": self.ac_id,
            "ip": self.ip,
            "info": info,
            "chksum": chksum,
            "n": "200",
            "type": "1",
        }
        time.sleep(_REQUEST_DELAY)
        self._log("🚀", "发起登录请求")
        resp = self._post(f"http://{self.gateway}/cgi-bin/srun_portal", payload)
        if not resp:
            return False
        if self._is_login_success(resp):
            self._log("🎉", "登录成功")
            return True

        self._log("❌", self.get_error_message(resp))
        return False

    def logout(self) -> bool:
        self.last_error = None

        ts = int(time.time() * 1000)
        payload = {
            "callback": self._callback(ts),
            "action": "logout",
            "username": self.username,
            "ac_id": self.ac_id,
            "ip": self.ip or "",
            "_": ts,
        }
        self._log("🐾", "发起登出请求")
        resp = self._get(f"http://{self.gateway}/cgi-bin/srun_portal", payload)
        if not resp:
            return False
        if self._is_login_success(resp):
            self._log("🎉", "登出成功")
            return True
        self._log("❌", self.get_error_message(resp))
        return False

    def check_status(self) -> bool:
        self.last_error = None

        ts = int(time.time() * 1000)
        params = {"callback": self._callback(ts), "_": ts}
        resp = self._get(f"http://{self.gateway}/cgi-bin/rad_user_info", params)
        if not resp:
            return False
        if "not_online" in resp:
            return False
        return True

    # ------------------------------------------------------------------
    # Error interpretation
    # ------------------------------------------------------------------

    def get_last_error(self) -> Optional[ErrorCode]:
        return self.last_error

    def get_error_message(self, resp_text: str) -> str:
        data = self._extract_json(resp_text)
        error = None
        error_msg = None
        if data:
            error = data.get("error") or data.get("res")
            error_msg = data.get("error_msg")

        if error is not None and error in _SRUN_ERROR_MAP:
            self.last_error = _SRUN_ERROR_MAP[error]
            ec = self.last_error
            return ec.full_message() if ec else f"登录失败: {error}"

        if "already" in resp_text or "在线" in resp_text:
            self.last_error = ErrorCode.ALREADY_ONLINE
            return ErrorCode.ALREADY_ONLINE.format()

        if error_msg:
            self.last_error = ErrorCode.LOGIN_RESPONSE_UNKNOWN
            return f"登录失败: {error_msg}"

        self.last_error = ErrorCode.LOGIN_RESPONSE_UNKNOWN
        return f"登录失败: {error or resp_text.strip()}"

"""Pre-flight network checks run before attempting login.

Each function returns an optional ErrorCode so callers can present
user-friendly feedback before wasting time on a doomed login.
"""

from __future__ import annotations

import logging
import socket
import sys
from typing import List, Optional

from errors import ErrorCode

_LOGGER = logging.getLogger(__name__)


def get_network_interfaces() -> List[str]:
    """Return a list of active, non-loopback interface names.

    Prefers ``netifaces`` when available; falls back to a
    ``socket.getaddrinfo``-based heuristic on platforms without it.
    """
    try:
        import netifaces as ni  # type: ignore[import-untyped]
    except ImportError:
        return _get_interfaces_fallback()

    names: List[str] = []
    for iface in ni.interfaces():
        try:
            addrs = ni.ifaddresses(iface)
        except ValueError:
            continue
        # AF_INET = 2; skip loopback
        inet_addrs = addrs.get(2, [])
        for addr in inet_addrs:
            ip = addr.get("addr", "")
            if ip and not ip.startswith("127."):
                names.append(iface)
                break
    return names


def _get_interfaces_fallback() -> List[str]:
    """Best-effort interface list via the standard library."""
    names: List[str] = []
    try:
        hostname = socket.gethostname()
        info = socket.getaddrinfo(hostname, None)
        seen = set()
        for (_family, _type, _proto, _canonname, sockaddr) in info:
            ip = sockaddr[0]
            if not ip.startswith("127.") and ip not in seen:
                seen.add(ip)
    except OSError:
        pass
    # On Windows we can also query socket.if_nameindex()
    if hasattr(socket, "if_nameindex"):
        try:
            for _idx, name in socket.if_nameindex():
                if name.lower().startswith("lo"):
                    continue
                names.append(name)
        except OSError:
            pass
    return names


def is_network_available() -> bool:
    """Return True when at least one non-loopback interface is present."""
    return len(get_network_interfaces()) > 0


def check_network_interfaces() -> Optional[ErrorCode]:
    """Verify the machine has usable network hardware."""
    if not is_network_available():
        return ErrorCode.NO_NETWORK_INTERFACE
    return None


def check_gateway_reachable(gateway: str, timeout: float = 3.0) -> Optional[ErrorCode]:
    """TCP-connect to *gateway*:80 to test basic reachability."""
    try:
        with socket.create_connection((gateway, 80), timeout=timeout):
            pass
        return None
    except OSError:
        return ErrorCode.GATEWAY_UNREACHABLE


def check_dns_resolution(hostname: str = "www.baidu.com") -> Optional[ErrorCode]:
    """Resolve an external hostname to verify DNS works."""
    try:
        socket.getaddrinfo(hostname, 80)
        return None
    except OSError:
        return ErrorCode.DNS_RESOLUTION_FAILED


def run_preflight_checks(gateway: str) -> List[ErrorCode]:
    """Run all pre-flight checks and return every error found.

    Returns an empty list when everything looks good.
    """
    errors: List[ErrorCode] = []
    err = check_network_interfaces()
    if err is not None:
        errors.append(err)
        # If we have NO interfaces, further checks are pointless.
        return errors
    err = check_gateway_reachable(gateway)
    if err is not None:
        errors.append(err)
    err = check_dns_resolution()
    if err is not None:
        errors.append(err)
    return errors

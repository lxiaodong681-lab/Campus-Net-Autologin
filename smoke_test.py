"""Minimal smoke tests for core modules."""

from __future__ import annotations


def test_crypto() -> None:
    """Verify encryption helpers produce expected output shapes."""
    from srun_login import get_base64, get_md5, get_sha1, xencode

    encrypted = xencode("test_msg", "test_key")
    assert isinstance(encrypted, bytes), "xencode should return bytes"
    assert len(encrypted) > 0, "xencode should produce non-empty output"

    b64 = get_base64(b"hello world")
    assert isinstance(b64, str) and len(b64) > 0, "get_base64 should return non-empty str"

    md5 = get_md5("pass", "token")
    assert md5.startswith("{MD5}"), "get_md5 should produce {MD5} prefix"

    sha1 = get_sha1("value")
    assert len(sha1) == 40, "SHA1 hex digest should be 40 chars"


def test_login_success_detection() -> None:
    """_is_login_success must NOT produce false positives from 'suc' substring."""
    from srun_login import SRUNLogin

    login = SRUNLogin("u", "p", "127.0.0.1", "1")
    # "suc" appearing inside a longer word should NOT count as success
    assert not login._is_login_success('{"error":"unknown","msg":"successful hack"}'), (
        "'suc' substring should not be treated as success"
    )
    # Real success patterns
    assert login._is_login_success("login_ok"), "login_ok should be success"
    assert login._is_login_success('{"error":"ok"}'), '"error":"ok" should be success'
    assert login._is_login_success('{"error":"ok","data":{}}'), "error==ok in JSON should be success"


def test_config_path() -> None:
    """ConfigManager creates its directory and uses the expected file name."""
    from config_manager import ConfigManager

    cm = ConfigManager()
    assert cm.config_dir.exists(), "Config dir should exist after init"
    assert cm.config_path.name == "config.json", "Config file should be named config.json"


def test_error_codes() -> None:
    """Every ErrorCode has a non-empty code and message."""
    from errors import ErrorCode

    for member in ErrorCode:
        assert isinstance(member.code, int) and member.code > 0, f"{member} code invalid"
        assert member.message, f"{member} message is empty"


def test_login_credentials_namedtuple() -> None:
    """get_login_credentials returns None when no config, or LoginCredentials when filled."""
    from config_manager import ConfigManager, LoginCredentials

    cm = ConfigManager()
    creds = cm.get_login_credentials()
    # By default in a test environment there are no credentials
    assert creds is None or isinstance(creds, LoginCredentials)


def test_network_checker_noop() -> None:
    """Pre-flight checks run without crashing (may or may not find interfaces)."""
    from network_checker import run_preflight_checks

    errors = run_preflight_checks("127.0.0.1")
    assert isinstance(errors, list), "run_preflight_checks should return a list"


if __name__ == "__main__":
    print("Running smoke tests...")
    test_crypto()
    print("  [OK] crypto")
    test_login_success_detection()
    print("  [OK] login success detection")
    test_config_path()
    print("  [OK] config path")
    test_error_codes()
    print("  [OK] error codes")
    test_login_credentials_namedtuple()
    print("  [OK] login credentials")
    test_network_checker_noop()
    print("  [OK] network checker")
    print("All smoke tests passed.")

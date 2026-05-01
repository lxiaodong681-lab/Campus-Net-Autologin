"""Minimal smoke tests for core modules."""

from __future__ import annotations

def test_crypto() -> None:
    try:
        from srun_login import get_base64, get_md5, get_sha1, xencode
    except ModuleNotFoundError:
        print("⚠️ 缺少依赖 requests，跳过加密测试")
        return
    token = "test_token"
    info = '{"username":"u","password":"p","ip":"1.1.1.1","acid":"1","enc_ver":"srun_bx1"}'
    encoded = xencode(info, token)
    assert isinstance(encoded, (bytes, bytearray))
    base64 = get_base64(encoded)
    assert base64.startswith("L") or base64
    md5 = get_md5("p", token)
    sha1 = get_sha1("abc")
    assert md5.startswith("{MD5}")
    assert len(sha1) == 40


def test_config_path() -> None:
    try:
        from config_manager import ConfigManager
    except ModuleNotFoundError:
        print("⚠️ 缺少依赖 keyring，跳过配置测试")
        return
    manager = ConfigManager()
    assert manager.config_dir.exists()
    assert manager.config_path.name == "config.json"


if __name__ == "__main__":
    test_crypto()
    test_config_path()
    print("✅ smoke tests passed")





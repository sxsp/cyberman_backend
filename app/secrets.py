"""密钥管理：JWT 签名密钥与 Fernet 加密密钥。

优先读环境变量（生产）；未设置则首次启动生成并持久化到数据目录（权限 600），
保证重启后密钥稳定、开箱即用。
"""
from __future__ import annotations

import os
import secrets as _secrets
from pathlib import Path

from cryptography.fernet import Fernet

from . import config


def _load_or_create(path: Path, generator) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    value = generator()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    os.chmod(path, 0o600)
    return value


def jwt_secret() -> str:
    env = os.environ.get("SERVER1_JWT_SECRET", "")
    if env:
        return env
    return _load_or_create(
        config.data_dir() / "jwt_secret",
        lambda: _secrets.token_urlsafe(48),
    )


def fernet() -> Fernet:
    env = os.environ.get("SERVER1_FERNET_KEY", "")
    key = env or _load_or_create(
        config.data_dir() / "fernet_key",
        lambda: Fernet.generate_key().decode(),
    )
    return Fernet(key.encode())

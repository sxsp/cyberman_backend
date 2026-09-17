"""安全原语：口令散列（scrypt）、JWT、API key 加解密。"""
from __future__ import annotations

import hashlib
import os
import secrets as _secrets
import time

import jwt

from . import config
from .secrets import fernet, jwt_secret

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


# ---- 口令散列 ----

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, dk_hex = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return _secrets.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


# ---- JWT ----

def create_token(user_id: int) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + config.token_expire_minutes() * 60,
    }
    return jwt.encode(payload, jwt_secret(), algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[config.JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# ---- API key 加解密 ----

def encrypt_key(plaintext: str) -> str:
    return fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(token: str) -> str:
    return fernet().decrypt(token.encode()).decode()


def key_hint(plaintext: str) -> str:
    """脱敏提示：只保留头尾，列表接口绝不返回明文。"""
    if len(plaintext) <= 8:
        return "****"
    return f"{plaintext[:4]}****{plaintext[-4:]}"

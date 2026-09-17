"""配置：环境变量 + 最小 .env 加载。全部懒加载，便于测试用环境变量覆盖。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

JWT_ALGORITHM = "HS256"


def _load_dotenv() -> None:
    """最小 .env 加载（KEY=VALUE，# 注释，可选引号）。已存在的环境变量不覆盖。"""
    path = BASE_DIR / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else BASE_DIR / p


def data_dir() -> Path:
    return _resolve(os.environ.get("SERVER1_DATA_DIR", str(BASE_DIR / "data")))


def db_path() -> Path:
    return _resolve(os.environ.get("SERVER1_DB_PATH", str(data_dir() / "server1.db")))


def uploads_dir() -> Path:
    """人设肖像/语音等上传文件的存储根目录。"""
    return data_dir() / "uploads"


def token_expire_minutes() -> int:
    return int(os.environ.get("SERVER1_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))


_load_dotenv()

"""SQLite 数据层：连接 + 建表。单用户规模下零运维即可。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS personas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    label         TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    ref_text      TEXT NOT NULL DEFAULT '',
    ref_wav       TEXT NOT NULL DEFAULT '',
    ref_image     TEXT NOT NULL DEFAULT '',
    is_default    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_personas_user ON personas(user_id);

CREATE TABLE IF NOT EXISTS api_keys (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider      TEXT NOT NULL,
    base_url      TEXT NOT NULL DEFAULT '',
    key_encrypted TEXT NOT NULL,
    key_hint      TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_user_provider ON api_keys(user_id, provider);

CREATE TABLE IF NOT EXISTS memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    persona_id INTEGER REFERENCES personas(id) ON DELETE SET NULL,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """幂等迁移：老库补 api_keys.base_url 列。"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(api_keys)").fetchall()}
    if "base_url" not in cols:
        conn.execute(
            "ALTER TABLE api_keys ADD COLUMN base_url TEXT NOT NULL DEFAULT ''"
        )


def init_db(db_path: Path | None = None) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()

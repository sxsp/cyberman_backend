"""API 密钥：Fernet 加密落库，列表只返回脱敏 hint，绝不返回明文。

明文只在未来「注入 Server 2」时经 get_plaintext_key 内部解密使用，无对外明文接口。
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import security
from ..deps import get_current_user, get_db
from ..schemas import ApiKeyIn, ApiKeyOut

router = APIRouter(prefix="/api/keys", tags=["keys"])


@router.get("", response_model=list[ApiKeyOut])
def list_keys(
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[ApiKeyOut]:
    rows = conn.execute(
        "SELECT id, provider, key_hint, created_at FROM api_keys "
        "WHERE user_id = ? ORDER BY id",
        (user["id"],),
    ).fetchall()
    return [
        ApiKeyOut(id=r["id"], provider=r["provider"], key_hint=r["key_hint"], created_at=r["created_at"])
        for r in rows
    ]


@router.post("", response_model=ApiKeyOut, status_code=201)
def create_key(
    body: ApiKeyIn,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> ApiKeyOut:
    cur = conn.execute(
        "INSERT INTO api_keys (user_id, provider, key_encrypted, key_hint) VALUES (?, ?, ?, ?)",
        (user["id"], body.provider, security.encrypt_key(body.key), security.key_hint(body.key)),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, provider, key_hint, created_at FROM api_keys WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    return ApiKeyOut(
        id=row["id"], provider=row["provider"], key_hint=row["key_hint"], created_at=row["created_at"]
    )


@router.delete("/{key_id}", status_code=204)
def delete_key(
    key_id: int,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    row = conn.execute(
        "SELECT 1 FROM api_keys WHERE id = ? AND user_id = ?", (key_id, user["id"])
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="密钥不存在")
    conn.execute("DELETE FROM api_keys WHERE id = ? AND user_id = ?", (key_id, user["id"]))
    conn.commit()


def get_plaintext_key(conn: sqlite3.Connection, user_id: int, provider: str) -> str | None:
    """内部服务函数：取某 provider 最近一条密钥的明文（供 Server 2 注入，无路由暴露）。"""
    row = conn.execute(
        "SELECT key_encrypted FROM api_keys WHERE user_id = ? AND provider = ? "
        "ORDER BY id DESC LIMIT 1",
        (user_id, provider),
    ).fetchone()
    if row is None:
        return None
    return security.decrypt_key(row["key_encrypted"])

"""API 密钥：固定槽位（按 provider 唯一），Fernet 加密落库，列表只返回脱敏 hint。

明文只在「注入推理服务」时经 get_credentials 内部解密使用，无对外明文接口。
每个 provider（如 llm / kimi）只保留一条：PUT 覆盖更新，DELETE 按 provider 清除。
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import security
from ..deps import get_current_user, get_db
from ..schemas import ApiKeyOut, ApiKeySetIn, CredentialsOut

router = APIRouter(prefix="/api/keys", tags=["keys"])


def _to_out(row: sqlite3.Row) -> ApiKeyOut:
    return ApiKeyOut(
        id=row["id"],
        provider=row["provider"],
        key_hint=row["key_hint"],
        base_url=row["base_url"],
        model=row["model"],
        created_at=row["created_at"],
    )


@router.get("", response_model=list[ApiKeyOut])
def list_keys(
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[ApiKeyOut]:
    rows = conn.execute(
        "SELECT id, provider, key_hint, base_url, model, created_at FROM api_keys "
        "WHERE user_id = ? ORDER BY id",
        (user["id"],),
    ).fetchall()
    return [_to_out(r) for r in rows]


@router.put("/{provider}", response_model=ApiKeyOut)
def upsert_key(
    provider: str,
    body: ApiKeySetIn,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> ApiKeyOut:
    conn.execute(
        "INSERT INTO api_keys (user_id, provider, base_url, model, key_encrypted, key_hint) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, provider) DO UPDATE SET "
        "base_url = excluded.base_url, model = excluded.model, "
        "key_encrypted = excluded.key_encrypted, key_hint = excluded.key_hint, "
        "created_at = datetime('now')",
        (
            user["id"], provider, body.base_url, body.model,
            security.encrypt_key(body.key), security.key_hint(body.key),
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, provider, key_hint, base_url, model, created_at FROM api_keys "
        "WHERE user_id = ? AND provider = ?",
        (user["id"], provider),
    ).fetchone()
    return _to_out(row)


@router.delete("/{provider}", status_code=204)
def delete_key(
    provider: str,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    cur = conn.execute(
        "DELETE FROM api_keys WHERE user_id = ? AND provider = ?", (user["id"], provider)
    )
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="密钥不存在")


@router.get("/{provider}/credentials", response_model=CredentialsOut)
def key_credentials(
    provider: str,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> CredentialsOut:
    cred = get_credentials(conn, user["id"], provider)
    if cred is None:
        raise HTTPException(status_code=404, detail="密钥未设置")
    return CredentialsOut(**cred)


def get_credentials(
    conn: sqlite3.Connection, user_id: int, provider: str
) -> dict | None:
    """内部服务函数：取某 provider 的 {base_url, model, key 明文}（供 LLM 调用）。"""
    row = conn.execute(
        "SELECT base_url, model, key_encrypted FROM api_keys "
        "WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    ).fetchone()
    if row is None:
        return None
    return {
        "base_url": row["base_url"],
        "model": row["model"],
        "key": security.decrypt_key(row["key_encrypted"]),
    }

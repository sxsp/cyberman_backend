"""聊天记录：按人设持久化消息。LLM 调用由前端直连完成，后端只存历史。"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user, get_db
from ..schemas import MessageOut, TurnIn

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _owned_persona(conn: sqlite3.Connection, user_id: int, persona_id: int) -> None:
    row = conn.execute(
        "SELECT 1 FROM personas WHERE id = ? AND user_id = ?", (persona_id, user_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="人设不存在")


@router.get("/{persona_id}/history", response_model=list[MessageOut])
def history(
    persona_id: int,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[MessageOut]:
    _owned_persona(conn, user["id"], persona_id)
    rows = conn.execute(
        "SELECT id, role, content, created_at FROM messages "
        "WHERE user_id = ? AND persona_id = ? ORDER BY id",
        (user["id"], persona_id),
    ).fetchall()
    return [
        MessageOut(id=r["id"], role=r["role"], content=r["content"], created_at=r["created_at"])
        for r in rows
    ]


@router.post("/{persona_id}/append", status_code=204)
def append(
    persona_id: int,
    body: TurnIn,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    _owned_persona(conn, user["id"], persona_id)
    conn.execute(
        "INSERT INTO messages (user_id, persona_id, role, content) VALUES (?, ?, 'user', ?)",
        (user["id"], persona_id, body.user_message),
    )
    conn.execute(
        "INSERT INTO messages (user_id, persona_id, role, content) VALUES (?, ?, 'assistant', ?)",
        (user["id"], persona_id, body.assistant_message),
    )
    conn.commit()

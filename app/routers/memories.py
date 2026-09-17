"""记忆：按用户 + 人设存储。检索用词元重叠打分（CJK 双字 + 英文分词），
作为语义检索（bge-m3 + qdrant）的轻量占位，接口保持不变即可替换。"""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_current_user, get_db
from ..schemas import MemoryIn, MemoryOut

router = APIRouter(prefix="/api/memories", tags=["memories"])

_CJK = re.compile(r"[\u4e00-\u9fff]")
_ALNUM = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    text = text.lower()
    tokens = set(_ALNUM.findall(text))
    cjk = _CJK.findall(text)
    for i in range(len(cjk) - 1):
        tokens.add(cjk[i] + cjk[i + 1])
    tokens.update(cjk)
    return tokens


def _to_out(row: sqlite3.Row) -> MemoryOut:
    return MemoryOut(
        id=row["id"], persona_id=row["persona_id"], text=row["text"], created_at=row["created_at"]
    )


def _owned_persona(conn: sqlite3.Connection, user_id: int, persona_id: int) -> None:
    row = conn.execute(
        "SELECT 1 FROM personas WHERE id = ? AND user_id = ?", (persona_id, user_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="人设不存在")


@router.post("", response_model=MemoryOut, status_code=201)
def add_memory(
    body: MemoryIn,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> MemoryOut:
    if body.persona_id is not None:
        _owned_persona(conn, user["id"], body.persona_id)
    cur = conn.execute(
        "INSERT INTO memories (user_id, persona_id, text) VALUES (?, ?, ?)",
        (user["id"], body.persona_id, body.text),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, persona_id, text, created_at FROM memories WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _to_out(row)


@router.get("", response_model=list[MemoryOut])
def search_memories(
    query: str = Query(min_length=1),
    persona_id: int | None = None,
    top_k: int = Query(5, ge=1, le=50),
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[MemoryOut]:
    if persona_id is not None:
        rows = conn.execute(
            "SELECT * FROM memories WHERE user_id = ? AND persona_id = ? ORDER BY id DESC",
            (user["id"], persona_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM memories WHERE user_id = ? ORDER BY id DESC", (user["id"],)
        ).fetchall()
    q = _tokenize(query)
    if not q:
        return []
    scored: list[tuple[float, sqlite3.Row]] = []
    for r in rows:
        t = _tokenize(r["text"])
        if not t:
            continue
        overlap = len(q & t)
        if overlap == 0:
            continue
        score = overlap / ((len(q) ** 0.5) * (len(t) ** 0.5))
        scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [_to_out(r) for _, r in scored[:top_k]]


@router.get("/recent", response_model=list[MemoryOut])
def recent_memories(
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[MemoryOut]:
    rows = conn.execute(
        "SELECT * FROM memories WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user["id"], limit),
    ).fetchall()
    return [_to_out(r) for r in rows]


@router.delete("/{memory_id}", status_code=204)
def delete_memory(
    memory_id: int,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    row = conn.execute(
        "SELECT 1 FROM memories WHERE id = ? AND user_id = ?", (memory_id, user["id"])
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    conn.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user["id"]))
    conn.commit()

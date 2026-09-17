"""文本聊天：按人设对话，记录历史，构建精简上下文（滚动摘要 + 最近消息）后调 LLM。

上下文策略：
- system = 人设 system_prompt
- 若历史超过 KEEP_RECENT 条，把更早的消息做「滚动摘要」（增量，缓存到
  conversation_summaries，只总结新溢出的部分），摘要作为第二条 system 注入
- 最近 KEEP_RECENT 条原样带上
"""
from __future__ import annotations

import logging
import sqlite3

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user, get_db
from ..schemas import MessageOut, SendIn
from .keys import get_credentials

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

KEEP_RECENT = 20
_LLM_PROVIDER = "llm"

_SUMMARIZE_SYSTEM = (
    "你是对话摘要助手。把给定对话历史压缩成简洁要点，保留关键事实、用户偏好、"
    "约定与未完成事项，用中文，不超过 300 字。"
)


def _llm_url(base_url: str) -> str:
    """把 base_url 归一化成完整 /chat/completions 地址（已含则不重复拼）。"""
    base = base_url.rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


async def _call_llm(cred: dict, messages: list[dict]) -> str:
    url = _llm_url(cred["base_url"])
    payload = {"model": cred["model"], "messages": messages, "stream": False}
    headers = {"Authorization": f"Bearer {cred['key']}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"LLM 请求失败：{e}") from e
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"LLM 返回 {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise HTTPException(status_code=502, detail="LLM 返回格式异常") from e


async def _summarize(cred: dict, text: str) -> str:
    return await _call_llm(
        cred,
        [{"role": "system", "content": _SUMMARIZE_SYSTEM}, {"role": "user", "content": text}],
    )


async def _rolling_summary(
    conn: sqlite3.Connection, user_id: int, persona_id: int,
    old_messages: list[sqlite3.Row], cred: dict,
) -> str:
    """增量滚动摘要：只总结「未总结过的新溢出消息」，与已有摘要合并。"""
    cached = conn.execute(
        "SELECT summary, last_message_id FROM conversation_summaries "
        "WHERE user_id = ? AND persona_id = ?",
        (user_id, persona_id),
    ).fetchone()
    existing = cached["summary"] if cached else ""
    last_id = cached["last_message_id"] if cached else 0

    new_old = [m for m in old_messages if m["id"] > last_id]
    if not new_old:
        return existing

    text = (existing + "\n\n" if existing else "") + "\n".join(
        f"{m['role']}: {m['content']}" for m in new_old
    )
    try:
        summary = await _summarize(cred, text)
    except HTTPException:
        logger.exception("摘要生成失败，本轮不带摘要继续")
        return existing

    conn.execute(
        "INSERT INTO conversation_summaries (user_id, persona_id, summary, last_message_id) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, persona_id) DO UPDATE SET "
        "summary = excluded.summary, last_message_id = excluded.last_message_id, "
        "updated_at = datetime('now')",
        (user_id, persona_id, summary, old_messages[-1]["id"]),
    )
    conn.commit()
    return summary


async def _build_context(
    conn: sqlite3.Connection, user_id: int, persona_id: int,
    system_prompt: str, cred: dict,
) -> list[dict]:
    rows = conn.execute(
        "SELECT id, role, content FROM messages "
        "WHERE user_id = ? AND persona_id = ? ORDER BY id",
        (user_id, persona_id),
    ).fetchall()
    recent = list(rows[-KEEP_RECENT:]) if len(rows) > KEEP_RECENT else list(rows)
    old = list(rows[:-KEEP_RECENT]) if len(rows) > KEEP_RECENT else []

    msgs: list[dict] = [{"role": "system", "content": system_prompt or "你是一个友好的助手。"}]
    if old:
        summary = await _rolling_summary(conn, user_id, persona_id, old, cred)
        if summary:
            msgs.append({
                "role": "system",
                "content": "以下是此前对话的摘要，请自然参考，不要逐条复述：\n" + summary,
            })
    msgs += [{"role": m["role"], "content": m["content"]} for m in recent]
    return msgs


def _owned_persona(conn: sqlite3.Connection, user_id: int, persona_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM personas WHERE id = ? AND user_id = ?", (persona_id, user_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="人设不存在")
    return row


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


@router.post("/{persona_id}/send", response_model=MessageOut)
async def send(
    persona_id: int,
    body: SendIn,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> MessageOut:
    persona = _owned_persona(conn, user["id"], persona_id)

    cred = get_credentials(conn, user["id"], _LLM_PROVIDER)
    if not cred or not cred["base_url"] or not cred["key"] or not cred["model"]:
        raise HTTPException(status_code=400, detail="请先在「接口」页设置对话模型（base_url + 模型 + key）")

    # 记录用户消息
    conn.execute(
        "INSERT INTO messages (user_id, persona_id, role, content) VALUES (?, ?, 'user', ?)",
        (user["id"], persona_id, body.message),
    )
    conn.commit()

    context = await _build_context(conn, user["id"], persona_id, persona["system_prompt"], cred)
    reply = await _call_llm(cred, context)

    cur = conn.execute(
        "INSERT INTO messages (user_id, persona_id, role, content) VALUES (?, ?, 'assistant', ?)",
        (user["id"], persona_id, reply),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, role, content, created_at FROM messages WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return MessageOut(id=row["id"], role=row["role"], content=row["content"], created_at=row["created_at"])

"""人设 CRUD：按用户隔离。人设结构对齐 AniMind 的 persona frontmatter
（name/label/system_prompt/ref_text/ref_wav/ref_image）。"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user, get_db
from ..schemas import PersonaIn, PersonaOut

router = APIRouter(prefix="/api/personas", tags=["personas"])


def _to_out(row: sqlite3.Row) -> PersonaOut:
    return PersonaOut(
        id=row["id"],
        name=row["name"],
        label=row["label"],
        system_prompt=row["system_prompt"],
        ref_text=row["ref_text"],
        ref_wav=row["ref_wav"],
        ref_image=row["ref_image"],
        is_default=bool(row["is_default"]),
    )


def _get_owned(conn: sqlite3.Connection, user_id: int, persona_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM personas WHERE id = ? AND user_id = ?", (persona_id, user_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="人设不存在")
    return row


@router.get("", response_model=list[PersonaOut])
def list_personas(
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[PersonaOut]:
    rows = conn.execute(
        "SELECT * FROM personas WHERE user_id = ? ORDER BY id", (user["id"],)
    ).fetchall()
    return [_to_out(r) for r in rows]


@router.post("", response_model=PersonaOut, status_code=201)
def create_persona(
    body: PersonaIn,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> PersonaOut:
    if body.is_default:
        conn.execute("UPDATE personas SET is_default = 0 WHERE user_id = ?", (user["id"],))
    cur = conn.execute(
        """
        INSERT INTO personas
            (user_id, name, label, system_prompt, ref_text, ref_wav, ref_image, is_default)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"], body.name, body.label, body.system_prompt,
            body.ref_text, body.ref_wav, body.ref_image, int(body.is_default),
        ),
    )
    conn.commit()
    return _to_out(_get_owned(conn, user["id"], cur.lastrowid))


@router.get("/{persona_id}", response_model=PersonaOut)
def get_persona(
    persona_id: int,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> PersonaOut:
    return _to_out(_get_owned(conn, user["id"], persona_id))


@router.put("/{persona_id}", response_model=PersonaOut)
def update_persona(
    persona_id: int,
    body: PersonaIn,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> PersonaOut:
    _get_owned(conn, user["id"], persona_id)
    if body.is_default:
        conn.execute("UPDATE personas SET is_default = 0 WHERE user_id = ?", (user["id"],))
    conn.execute(
        """
        UPDATE personas SET
            name = ?, label = ?, system_prompt = ?, ref_text = ?,
            ref_wav = ?, ref_image = ?, is_default = ?, updated_at = datetime('now')
        WHERE id = ? AND user_id = ?
        """,
        (
            body.name, body.label, body.system_prompt, body.ref_text,
            body.ref_wav, body.ref_image, int(body.is_default), persona_id, user["id"],
        ),
    )
    conn.commit()
    return _to_out(_get_owned(conn, user["id"], persona_id))


@router.delete("/{persona_id}", status_code=204)
def delete_persona(
    persona_id: int,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    _get_owned(conn, user["id"], persona_id)
    conn.execute(
        "DELETE FROM personas WHERE id = ? AND user_id = ?", (persona_id, user["id"])
    )
    conn.commit()

"""人设 CRUD：按用户隔离，支持肖像/语音文件上传。

人设结构对齐 AniMind 的 persona frontmatter（name/label/system_prompt/ref_text/
ref_image/ref_wav）。图片与语音以文件形式存 uploads/，DB 存本地路径，经
GET /api/personas/{id}/image|voice 鉴权读取（不暴露服务器路径）。
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config
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
        is_default=bool(row["is_default"]),
        has_image=bool(row["ref_image"]) and Path(row["ref_image"]).is_file(),
        has_voice=bool(row["ref_wav"]) and Path(row["ref_wav"]).is_file(),
    )


def _get_owned(conn: sqlite3.Connection, user_id: int, persona_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM personas WHERE id = ? AND user_id = ?", (persona_id, user_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="人设不存在")
    return row


async def _save_upload(
    user_id: int, persona_id: int, upload: UploadFile, kind: str
) -> str:
    ext = Path(upload.filename or "").suffix.lower() or (
        ".png" if kind == "image" else ".wav"
    )
    directory = config.uploads_dir() / str(user_id) / str(persona_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{kind}{ext}"
    path.write_bytes(await upload.read())
    return str(path)


def _remove_files(user_id: int, persona_id: int) -> None:
    shutil.rmtree(
        config.uploads_dir() / str(user_id) / str(persona_id), ignore_errors=True
    )


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
async def create_persona(
    name: str = Form(...),
    system_prompt: str = Form(""),
    label: str = Form(""),
    ref_text: str = Form(""),
    is_default: bool = Form(False),
    image: UploadFile | None = File(None),
    voice: UploadFile | None = File(None),
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> PersonaOut:
    if is_default:
        conn.execute("UPDATE personas SET is_default = 0 WHERE user_id = ?", (user["id"],))
    cur = conn.execute(
        "INSERT INTO personas (user_id, name, label, system_prompt, ref_text, is_default) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user["id"], name, label, system_prompt, ref_text, int(is_default)),
    )
    persona_id = cur.lastrowid
    ref_image = await _save_upload(user["id"], persona_id, image, "image") if image else ""
    ref_wav = await _save_upload(user["id"], persona_id, voice, "voice") if voice else ""
    if ref_image or ref_wav:
        conn.execute(
            "UPDATE personas SET ref_image = ?, ref_wav = ? WHERE id = ?",
            (ref_image, ref_wav, persona_id),
        )
    conn.commit()
    return _to_out(_get_owned(conn, user["id"], persona_id))


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
        "UPDATE personas SET name = ?, label = ?, system_prompt = ?, ref_text = ?, "
        "is_default = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
        (
            body.name, body.label, body.system_prompt, body.ref_text,
            int(body.is_default), persona_id, user["id"],
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
    _remove_files(user["id"], persona_id)
    conn.execute(
        "DELETE FROM personas WHERE id = ? AND user_id = ?", (persona_id, user["id"])
    )
    conn.commit()


@router.get("/{persona_id}/image")
async def persona_image(
    persona_id: int,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = _get_owned(conn, user["id"], persona_id)
    path = row["ref_image"]
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="肖像不存在")
    return FileResponse(path)


@router.get("/{persona_id}/voice")
async def persona_voice(
    persona_id: int,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = _get_owned(conn, user["id"], persona_id)
    path = row["ref_wav"]
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="语音不存在")
    return FileResponse(path)

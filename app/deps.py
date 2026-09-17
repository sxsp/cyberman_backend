"""FastAPI 依赖：数据库连接 + 当前用户鉴权。"""
from __future__ import annotations

import sqlite3

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db, security

_bearer = HTTPBearer(auto_error=False)


def get_db():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    user_id = security.decode_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    row = conn.execute(
        "SELECT id, username FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return {"id": row["id"], "username": row["username"]}

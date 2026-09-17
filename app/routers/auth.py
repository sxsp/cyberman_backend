"""账号鉴权：注册 / 登录 / 当前用户。"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import security
from ..deps import get_current_user, get_db
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, conn: sqlite3.Connection = Depends(get_db)) -> TokenOut:
    exists = conn.execute(
        "SELECT 1 FROM users WHERE username = ?", (body.username,)
    ).fetchone()
    if exists:
        raise HTTPException(status_code=409, detail="用户名已存在")
    cur = conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (body.username, security.hash_password(body.password)),
    )
    conn.commit()
    return TokenOut(access_token=security.create_token(cur.lastrowid))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, conn: sqlite3.Connection = Depends(get_db)) -> TokenOut:
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE username = ?", (body.username,)
    ).fetchone()
    if row is None or not security.verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return TokenOut(access_token=security.create_token(row["id"]))


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)) -> UserOut:
    return UserOut(**user)

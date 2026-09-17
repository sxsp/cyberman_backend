"""应用工厂：建表 + 挂载路由。测试可设环境变量后调用 create_app() 获得隔离实例。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .routers import auth, chat, keys, memories, personas


def create_app() -> FastAPI:
    db.init_db()
    app = FastAPI(title="Server1 控制面", version="0.1.0")
    # token 走 Header（非 cookie），allow_origins=* 可安全放开，便于 Web/移动端调试
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(personas.router)
    app.include_router(keys.router)
    app.include_router(memories.router)
    app.include_router(chat.router)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app

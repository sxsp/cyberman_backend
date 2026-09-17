"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str


class PersonaIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    label: str = Field(default="", max_length=128)
    system_prompt: str = ""
    ref_text: str = ""
    is_default: bool = False


class PersonaOut(BaseModel):
    id: int
    name: str
    label: str
    system_prompt: str
    ref_text: str
    is_default: bool
    has_image: bool = False
    has_voice: bool = False


class ApiKeyIn(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=512)


class ApiKeyOut(BaseModel):
    id: int
    provider: str
    key_hint: str
    created_at: str


class MemoryIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    persona_id: int | None = None


class MemoryOut(BaseModel):
    id: int
    persona_id: int | None
    text: str
    created_at: str

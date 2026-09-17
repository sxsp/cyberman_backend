"""Server1 控制面 API 端到端测试。"""
from __future__ import annotations


def _register(client, username="alice", password="secret123"):
    return client.post("/api/auth/register", json={"username": username, "password": password})


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- 基础 ----

def test_healthz(client):
    assert client.get("/healthz").json() == {"ok": True}


# ---- 账号 ----

def test_register_login_me(client):
    r = _register(client)
    assert r.status_code == 201
    token = r.json()["access_token"]

    me = client.get("/api/auth/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["username"] == "alice"

    ok = client.post("/api/auth/login", json={"username": "alice", "password": "secret123"})
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert bad.status_code == 401


def test_register_duplicate(client):
    assert _register(client).status_code == 201
    assert _register(client).status_code == 409


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=_auth("garbage")).status_code == 401


# ---- 人设 ----

def test_persona_crud(client):
    token = _register(client).json()["access_token"]
    h = _auth(token)

    r = client.post(
        "/api/personas",
        data={"name": "塔菲", "label": "塔菲", "system_prompt": "你是主播", "is_default": "true"},
        headers=h,
    )
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["is_default"] is True

    lst = client.get("/api/personas", headers=h)
    assert len(lst.json()) == 1

    r2 = client.put(
        f"/api/personas/{pid}",
        json={"name": "塔菲2", "label": "塔菲2", "system_prompt": "x", "is_default": True},
        headers=h,
    )
    assert r2.json()["name"] == "塔菲2"

    assert client.delete(f"/api/personas/{pid}", headers=h).status_code == 204
    assert client.get("/api/personas", headers=h).json() == []


def test_persona_default_uniqueness(client):
    token = _register(client).json()["access_token"]
    h = _auth(token)
    a = client.post("/api/personas", data={"name": "A", "is_default": "true"}, headers=h).json()
    b = client.post("/api/personas", data={"name": "B", "is_default": "true"}, headers=h).json()
    defaults = [p for p in client.get("/api/personas", headers=h).json() if p["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == b["id"]


def test_persona_isolation(client):
    t1 = _register(client, "alice").json()["access_token"]
    t2 = _register(client, "bob").json()["access_token"]
    pid = client.post("/api/personas", data={"name": "A"}, headers=_auth(t1)).json()["id"]
    assert client.get(f"/api/personas/{pid}", headers=_auth(t2)).status_code == 404
    assert client.delete(f"/api/personas/{pid}", headers=_auth(t2)).status_code == 404


def test_persona_upload_image_and_voice(client):
    token = _register(client).json()["access_token"]
    h = _auth(token)
    r = client.post(
        "/api/personas",
        data={"name": "塔菲", "system_prompt": "x"},
        files={
            "image": ("ref.png", b"\x89PNG\r\n\x1a\n" + b"0" * 16, "image/png"),
            "voice": ("ref.wav", b"RIFF" + b"0" * 16, "audio/wav"),
        },
        headers=h,
    )
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["has_image"] is True
    assert r.json()["has_voice"] is True

    img = client.get(f"/api/personas/{pid}/image", headers=h)
    assert img.status_code == 200
    assert img.content.startswith(b"\x89PNG")

    voice = client.get(f"/api/personas/{pid}/voice", headers=h)
    assert voice.status_code == 200
    assert voice.content.startswith(b"RIFF")

    # 未登录不能拉肖像
    assert client.get(f"/api/personas/{pid}/image").status_code == 401


# ---- API 密钥 ----

def test_api_key_fixed_slot_upsert(client):
    token = _register(client).json()["access_token"]
    h = _auth(token)
    secret = "sk-abcdef1234567890"
    # 设置（含 base_url）
    r = client.put(
        "/api/keys/llm",
        json={"key": secret, "base_url": "https://api.deepseek.com/v1"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["provider"] == "llm"
    assert r.json()["key_hint"] == "sk-a****7890"
    assert r.json()["base_url"] == "https://api.deepseek.com/v1"
    assert secret not in str(r.json())

    lst = client.get("/api/keys", headers=h).json()
    assert len(lst) == 1
    assert "key_encrypted" not in lst[0]
    assert secret not in str(lst)

    # 同 provider 覆盖，不新增
    client.put("/api/keys/llm", json={"key": "sk-new1234567890", "base_url": "https://x"}, headers=h)
    lst2 = client.get("/api/keys", headers=h).json()
    assert len(lst2) == 1
    assert lst2[0]["key_hint"] == "sk-n****7890"
    assert lst2[0]["base_url"] == "https://x"

    # 清除
    assert client.delete("/api/keys/llm", headers=h).status_code == 204
    assert client.get("/api/keys", headers=h).json() == []


# ---- 记忆 ----

def test_memory_add_search_delete(client):
    token = _register(client).json()["access_token"]
    h = _auth(token)
    pid = client.post("/api/personas", data={"name": "P"}, headers=h).json()["id"]

    a = client.post("/api/memories", json={"text": "用户在减脂", "persona_id": pid}, headers=h)
    assert a.status_code == 201
    client.post("/api/memories", json={"text": "用户喜欢打游戏", "persona_id": pid}, headers=h)

    s = client.get("/api/memories", params={"query": "减脂"}, headers=h)
    assert s.status_code == 200
    assert s.json()[0]["text"] == "用户在减脂"

    rec = client.get("/api/memories/recent", headers=h).json()
    assert len(rec) == 2

    assert client.delete(f"/api/memories/{a.json()['id']}", headers=h).status_code == 204


def test_memory_persona_ownership(client):
    t1 = _register(client, "alice").json()["access_token"]
    t2 = _register(client, "bob").json()["access_token"]
    pid = client.post("/api/personas", data={"name": "P"}, headers=_auth(t1)).json()["id"]
    r = client.post("/api/memories", json={"text": "x", "persona_id": pid}, headers=_auth(t2))
    assert r.status_code == 404

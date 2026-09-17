import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """每个测试用独立的数据目录 + 数据库，避免串扰。"""
    monkeypatch.setenv("SERVER1_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SERVER1_DB_PATH", str(tmp_path / "test.db"))
    from app.factory import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.notification_service import register_device_token
from web_app import app


def test_register_device_token_adds_unique_token(tmp_path, monkeypatch):
    token_file = tmp_path / "device_tokens.json"
    monkeypatch.setattr("backend.notification_service.DEVICE_TOKEN_FILE", token_file)
    monkeypatch.setattr("backend.notification_service.MOBILE_TOKEN_FILE", token_file)
    monkeypatch.setattr("backend.notification_service.WEB_TOKEN_FILE", token_file)

    tokens = register_device_token("token-001")
    assert tokens == ["token-001"]

    second = register_device_token("token-001")
    assert second == ["token-001"]

    persisted = json.loads(token_file.read_text(encoding="utf-8"))
    assert persisted == ["token-001"]


def test_login_includes_student_code():
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"username": "student", "password": "student123"})

    assert response.status_code == 200
    data = response.json()
    assert data["user"]["student_id"] == "HS-001"

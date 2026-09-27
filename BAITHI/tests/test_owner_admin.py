from __future__ import annotations

import json

from fastapi.testclient import TestClient

from auth_service import register_user
from owner_auth import create_user_token
from owner_service import record_successful_feature_use
from web_app import app


def configure_owner(monkeypatch, tmp_path):
    user_file = tmp_path / "users.json"
    usage_file = tmp_path / "feature_usage.json"
    monkeypatch.setattr("auth_service.USERS_FILE", user_file)
    monkeypatch.setattr("owner_service.USAGE_FILE", usage_file)
    monkeypatch.setenv("OWNER_USERNAME", "site-owner")
    monkeypatch.setenv("OWNER_PASSWORD", "A-strong-owner-password-92")
    monkeypatch.setenv("STUDYSYNC_SESSION_SECRET", "session-secret-for-tests-0123456789")
    return user_file, usage_file


def test_owner_has_separate_login_and_can_manage_users(tmp_path, monkeypatch):
    configure_owner(monkeypatch, tmp_path)
    user = register_user("student01", "StudentPass1", "student", "Học sinh 1", "8A1")
    record_successful_feature_use(user["username"], "assignments")
    client = TestClient(app)

    assert client.post("/api/auth/register", json={
        "username": "new-owner",
        "password": "OwnerPass123",
        "role": "owner",
    }).status_code == 400
    assert client.get("/api/owner/overview").status_code == 401

    login = client.post("/api/owner/login", json={
        "username": "site-owner",
        "password": "A-strong-owner-password-92",
    })
    assert login.status_code == 200
    owner_headers = {"Authorization": f"Bearer {login.json()['token']}"}

    overview = client.get("/api/owner/overview", headers=owner_headers)
    assert overview.status_code == 200
    assert overview.json()["users"]["used_features"] == 1
    assert overview.json()["feature_usage"]["assignments"] == 1

    users = client.get("/api/owner/users", headers=owner_headers)
    assert users.status_code == 200
    assert len(users.json()["users"]) == 1
    assert "password" not in users.json()["users"][0]

    status = client.patch(
        f"/api/owner/users/{user['id']}/status",
        headers=owner_headers,
        json={"is_active": False},
    )
    assert status.status_code == 200
    user_token = create_user_token("student01", "student")
    assert client.get(
        "/api/dashboard/student?username=student01",
        headers={"Authorization": f"Bearer {user_token}"},
    ).status_code == 403
    assert client.post("/api/auth/login", json={
        "username": "student01", "password": "StudentPass1",
    }).status_code == 401


def test_only_valid_user_session_counts_feature_use(tmp_path, monkeypatch):
    user_file, usage_file = configure_owner(monkeypatch, tmp_path)
    register_user("student01", "StudentPass1", "student", "Học sinh 1", "8A1")
    client = TestClient(app)
    payload = {
        "session": "morning",
        "day": "2",
        "period": 1,
        "subject": "Toán",
        "lecturer": "Cô An",
        "username": "student01",
    }

    assert client.put("/api/schedule/slot", json=payload).status_code == 401
    assert client.put(
        "/api/schedule/slot",
        headers={"Authorization": "Bearer invalid"},
        json=payload,
    ).status_code == 401

    token = create_user_token("student01", "student")
    response = client.put(
        "/api/schedule/slot",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 200
    events = json.loads(usage_file.read_text(encoding="utf-8"))
    assert len(events) == 1
    assert events[0]["username"] == "student01"
    assert json.loads(user_file.read_text(encoding="utf-8"))["users"][0]["username"] == "student01"

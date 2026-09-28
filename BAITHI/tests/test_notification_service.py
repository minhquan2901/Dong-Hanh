from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from backend.notification_service import (
    get_user_web_tokens,
    register_device_token,
    register_user_web_token,
    send_due_task_reminders,
)
from auth_service import register_user
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


def test_web_push_tokens_are_scoped_to_desktop_account(tmp_path, monkeypatch):
    subscriptions = tmp_path / "web_push_subscriptions.json"
    monkeypatch.setattr("backend.notification_service.WEB_PUSH_SUBSCRIPTIONS_FILE", subscriptions)

    assert register_user_web_token("student-a", "desktop-token-1") == 1
    assert register_user_web_token("student-a", "desktop-token-1") == 1
    assert register_user_web_token("student-a", "desktop-token-2") == 2
    assert register_user_web_token("student-b", "desktop-token-3") == 1
    assert get_user_web_tokens("student-a") == ["desktop-token-1", "desktop-token-2"]
    assert get_user_web_tokens("student-b") == ["desktop-token-3"]


def test_web_push_routes_serve_worker_and_register_student_token(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(
        "backend.notification_service.WEB_PUSH_SUBSCRIPTIONS_FILE",
        tmp_path / "web_push_subscriptions.json",
    )
    register_user("student-a", "Pass1234", "student", "Học sinh A")
    client = TestClient(app)

    manifest = client.get("/manifest.json")
    student_page = client.get("/student")
    apple_icon = client.get("/static/studysync-apple-touch-icon-v2.png")
    worker = client.get("/firebase-messaging-sw.js")
    module = client.get("/firebase-notifications.js")
    registered = client.post("/api/push/register", json={
        "username": "student-a", "token": "desktop-token-1",
    })

    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert manifest.json()["display"] == "standalone"
    assert manifest.json()["name"] == "StudySync"
    assert manifest.json()["start_url"] == "/student"
    for icon in manifest.json()["icons"]:
        icon_response = client.get(icon["src"])
        assert icon_response.status_code == 200
        assert icon_response.headers["content-type"].startswith("image/png")
    assert 'rel="manifest" href="/manifest.json"' in student_page.text
    assert 'studysync-apple-touch-icon-v2.png' in student_page.text
    assert apple_icon.status_code == 200
    assert apple_icon.headers["content-type"].startswith("image/png")
    assert worker.status_code == 200
    assert "onBackgroundMessage" in worker.text
    assert module.status_code == 200
    assert registered.status_code == 200
    assert registered.json()["message"] == "Đã bật thông báo trên thiết bị này."
    assert registered.json()["registered_devices"] == 1
    assert registered.json()["registered_desktop_devices"] == 1


def test_create_assignment_persists_vietnam_due_time(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr("owner_service.USAGE_FILE", tmp_path / "feature_usage.json")
    monkeypatch.setattr("database.study_repository.data_file", lambda name: tmp_path / name)
    monkeypatch.setenv("STUDYSYNC_SESSION_SECRET", "test-session-secret-with-at-least-32-chars")
    register_user("student-time", "Pass1234", "student", "Học sinh")
    from owner_auth import create_user_token
    token = create_user_token("student-time", "student")
    client = TestClient(app)

    response = client.post("/api/assignments", headers={
        "Authorization": f"Bearer {token}",
    }, json={
        "title": "Bài Toán",
        "subject": "Toán",
        "due_date": "2026-09-30",
        "due_time": "20:45:00",
        "priority": "Cao",
        "username": "student-time",
    })

    assert response.status_code == 200
    assert response.json()["assignment"]["due_date"] == "2026-09-30T20:45:00+07:00"


def test_push_due_endpoint_requires_cron_secret(monkeypatch):
    monkeypatch.setenv("PUSH_CRON_SECRET", "test-secret")
    monkeypatch.setattr("web_app.send_due_task_reminders", lambda: [])
    client = TestClient(app)

    assert client.post("/api/internal/push-due").status_code == 403
    response = client.post("/api/internal/push-due", headers={"X-Cron-Secret": "test-secret"})
    assert response.status_code == 200
    assert response.json() == {"reminders": []}


def test_due_task_pushes_cover_four_time_offsets_once_each(tmp_path, monkeypatch):
    subscriptions = tmp_path / "web_push_subscriptions.json"
    reminder_state = tmp_path / "push_reminder_state.json"
    monkeypatch.setattr("backend.notification_service.WEB_PUSH_SUBSCRIPTIONS_FILE", subscriptions)
    monkeypatch.setattr("backend.notification_service.PUSH_REMINDER_STATE_FILE", reminder_state)
    monkeypatch.setattr(
        "database.study_repository.data_file",
        lambda name: tmp_path / name,
    )

    from bus.study_bus import StudyBus
    zone = ZoneInfo("Asia/Ho_Chi_Minh")
    now = datetime(2026, 9, 27, 12, 0, tzinfo=zone)
    offsets = [timedelta(days=1), timedelta(hours=1), timedelta(minutes=10), timedelta(minutes=5)]
    for index, offset in enumerate(offsets):
        due_at = now + offset
        StudyBus().repository.add_assignment(
            f"Bài {index}", "Toán", due_at.isoformat(), "Cao", "student-a"
        )

    sent = []
    monkeypatch.setattr(
        "backend.notification_service.send_web_push_to_user",
        lambda username, title, body, path: sent.append((username, title, body, path)) or [{"status": "sent"}],
    )
    register_user_web_token("student-a", "desktop-token-1")

    first = send_due_task_reminders(now=now)
    second = send_due_task_reminders(now=now)

    assert len(first) == 4 and all(item["sent"] for item in first)
    assert second == []
    assert len(sent) == 4
    assert all(item[0] == "student-a" for item in sent)
    assert {item[1] for item in sent} == {
        "Nhiệm vụ còn 1 ngày",
        "Nhiệm vụ còn 1 giờ",
        "Nhiệm vụ còn 10 phút",
        "Nhiệm vụ còn 5 phút",
    }


def test_legacy_date_only_deadline_uses_end_of_day():
    from backend.notification_service import _parse_assignment_due_at

    due_at = _parse_assignment_due_at("2026-09-30")

    assert due_at is not None
    assert due_at.isoformat() == "2026-09-30T23:59:00+07:00"

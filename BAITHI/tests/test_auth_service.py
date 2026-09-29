from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from auth_service import (
    assign_student_id_to_parent,
    authenticate_user,
    get_students_for_parent,
    register_user,
    set_secondary_pin,
    update_linked_student,
    verify_secondary_pin,
)
from fastapi.testclient import TestClient
from web_app import app


def test_register_and_login_user(tmp_path, monkeypatch):
    user_file = tmp_path / "users.json"
    monkeypatch.setattr("auth_service.USERS_FILE", user_file)

    user = register_user(
        username="student01",
        password="Abc12345",
        role="student",
        full_name="Nguyễn Văn A",
        class_name="10A1",
    )

    assert user["username"] == "student01"
    assert user["role"] == "student"
    assert user["full_name"] == "Nguyễn Văn A"

    logged_in = authenticate_user("student01", "Abc12345")
    assert logged_in is not None
    assert logged_in["username"] == "student01"

    persisted = json.loads(user_file.read_text(encoding="utf-8"))
    assert any(item["username"] == "student01" for item in persisted["users"])


def test_register_duplicate_username_raises(tmp_path, monkeypatch):
    user_file = tmp_path / "users.json"
    monkeypatch.setattr("auth_service.USERS_FILE", user_file)

    register_user("parent01", "Pass1234", "parent", "Phụ huynh A")

    try:
        register_user("parent01", "Pass1234", "parent", "Phụ huynh B")
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_corrupt_user_file_is_not_treated_as_empty_or_overwritten(tmp_path, monkeypatch):
    user_file = tmp_path / "users.json"
    user_file.write_text('{"users": [', encoding="utf-8")
    monkeypatch.setattr("auth_service.USERS_FILE", user_file)

    with pytest.raises(RuntimeError, match="Không đọc được dữ liệu tài khoản"):
        register_user("student01", "Pass1234", "student", "Học sinh A")

    assert user_file.read_text(encoding="utf-8") == '{"users": ['


def test_concurrent_duplicate_registration_keeps_one_account(tmp_path, monkeypatch):
    user_file = tmp_path / "users.json"
    monkeypatch.setattr("auth_service.USERS_FILE", user_file)

    def register():
        try:
            register_user("same-user", "Pass1234", "student", "Học sinh")
            return "created"
        except ValueError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: register(), range(2)))

    persisted = json.loads(user_file.read_text(encoding="utf-8"))
    assert sorted(outcomes) == ["created", "duplicate"]
    assert [item["username"] for item in persisted["users"]] == ["same-user"]


def test_parent_only_sees_linked_students(tmp_path, monkeypatch):
    user_file = tmp_path / "users.json"
    monkeypatch.setattr("auth_service.USERS_FILE", user_file)

    register_user("parent01", "Pass1234", "parent", "Phụ huynh A")
    register_user("student01", "Pass1234", "student", "Học sinh A", "10A1")
    register_user("student02", "Pass1234", "student", "Học sinh B", "10A2")

    assert get_students_for_parent("parent01") == []


def test_parent_links_by_student_id_and_updates_profile(tmp_path, monkeypatch):
    user_file = tmp_path / "users.json"
    monkeypatch.setattr("auth_service.USERS_FILE", user_file)

    register_user("parent01", "Pass1234", "parent", "Phụ huynh A")
    student = register_user("student01", "Pass1234", "student", "Học sinh A", "10A1")

    assert student["student_id"] == "HS-001"
    assign_student_id_to_parent("parent01", "HS-001")
    updated = update_linked_student("parent01", "HS-001", "Học sinh mới", "8A2", "HN", False)

    assert updated["full_name"] == "Học sinh mới"
    assert updated["class_name"] == "8A2"
    assert updated["avatar"] == "HN"
    assert updated["is_active"] is False


def test_secondary_pin_is_hashed_and_verified(tmp_path, monkeypatch):
    user_file = tmp_path / "users.json"
    monkeypatch.setattr("auth_service.USERS_FILE", user_file)
    register_user("student01", "Abc12345", "student", "Học sinh A", "8/1")

    assert set_secondary_pin("student01", "Abc12345", "4826")
    persisted_user = json.loads(user_file.read_text(encoding="utf-8"))["users"][0]

    assert persisted_user["secondary_pin_hash"] != "4826"
    assert verify_secondary_pin("student01", "4826")
    assert not verify_secondary_pin("student01", "4827")


def test_pin_login_and_schedule_without_pin(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    register_user("student01", "Abc12345", "student", "Học sinh A", "8/1")
    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "student01", "password": "Abc12345"})
    assert login.status_code == 200
    session_headers = {"Authorization": f"Bearer {login.json()['token']}"}

    setup = client.post("/api/security/pin", json={
        "username": "student01", "password": "Abc12345", "pin": "4826",
    }, headers=session_headers)
    assert setup.status_code == 200
    login_without_pin = client.post("/api/auth/login", json={"username": "student01", "password": "Abc12345"})
    assert login_without_pin.status_code == 200
    assert login_without_pin.json()["requires_pin"] is True
    assert client.post("/api/auth/login", json={"username": "student01", "password": "Abc12345", "pin": "4827"}).status_code == 401
    login_with_pin = client.post("/api/auth/login", json={"username": "student01", "password": "Abc12345", "pin": "4826"})
    assert login_with_pin.status_code == 200
    assert login_with_pin.json()["user"]["pin_login_enabled"] is True

    wrong_pin_disable = client.post("/api/security/pin-login", json={
        "username": "student01", "password": "Abc12345", "pin": "4827", "enabled": False,
    }, headers=session_headers)
    assert wrong_pin_disable.status_code == 400
    assert client.post("/api/auth/login", json={"username": "student01", "password": "Abc12345"}).json()["requires_pin"]

    disabled = client.post("/api/security/pin-login", json={
        "username": "student01", "password": "Abc12345", "pin": "4826", "enabled": False,
    }, headers=session_headers)
    assert disabled.status_code == 200
    assert client.post("/api/auth/login", json={"username": "student01", "password": "Abc12345"}).json().get("user")

    schedule = client.put("/api/schedule/slot", json={
        "session": "night", "day": "2", "period": 1, "subject": "Toán", "lecturer": "",
        "username": "student01",
    }, headers=session_headers)
    assert schedule.status_code == 400
    deletion = client.request(
        "DELETE", "/api/schedule/slot?username=student01",
        json={"session": "morning", "day": "2", "period": 99, "username": "student01"},
        headers=session_headers,
    )
    assert deletion.status_code == 404


def test_parent_can_register_without_full_name(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    response = TestClient(app).post("/api/auth/register", json={
        "username": "parent01", "password": "Abc12345", "role": "parent",
    })
    assert response.status_code == 200
    assert response.json()["user"]["full_name"] == "parent01"

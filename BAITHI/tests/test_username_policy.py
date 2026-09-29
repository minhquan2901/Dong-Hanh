from __future__ import annotations

from datetime import date

import pytest

from auth_service import authenticate_user, register_user, rename_user_account
from fastapi.testclient import TestClient
from bus.study_bus import StudyBus
from username_policy import (
    generate_suggested_username,
    identity_violations,
    scan_registered_users,
    validate_class_name,
    validate_display_name,
    validate_username,
)
from web_app import app


def test_username_policy_accepts_only_expected_format():
    assert validate_username("An_Nguyen11") == (True, "")
    assert not validate_username("1nguyen11")[0]
    assert not validate_username("an@nguyen")[0]
    assert not validate_username("qwerty")[0]
    assert not validate_username("admin_01")[0]
    assert not validate_username("aaaaaa")[0]


def test_username_allows_vietnamese_and_spaces():
    """Tên tieng Viet co dau va khoang trang phai duoc chap nhan."""
    for name in ["Thanh Mai", "Nguyễn Văn An", "Đặng Thu Hà", "Ngô Thị Mai"]:
        valid, message = validate_username(name)
        assert valid is True, f"{name} bi tu choi: {message}"


def test_username_rejects_bad_spacing_and_symbols():
    assert not validate_username(" ThanhMai")[0]
    assert not validate_username("ThanhMai ")[0]
    assert not validate_username("Thanh  Mai")[0]
    assert not validate_username("Thanh/Mai")[0]
    assert not validate_username("Thanh-Mai")[0]


def test_class_policy_accepts_only_grades_six_through_nine():
    assert validate_class_name(" 8 / 2 ") == (True, "8/2")
    assert not validate_class_name("5/1")[0]
    assert not validate_class_name("10A1")[0]
    assert not validate_class_name("9/4")[0]


def test_username_suggestions_use_ascii_and_do_not_require_birth_year():
    suggestions = generate_suggested_username("Nguyễn Văn An")
    assert suggestions
    assert all(validate_username(item)[0] for item in suggestions)
    assert suggestions[0] == "an_nguyen"


def test_identity_scan_tracks_violations_and_resolves_fixed_user(monkeypatch):
    state = {"enabled": True, "violations": [], "last_scan_at": None}
    monkeypatch.setattr("username_policy.load_document", lambda *_args, **_kwargs: state.copy())

    def save_document(_key, value):
        state.update(value)

    monkeypatch.setattr("username_policy.save_document", save_document)
    user = {
        "username": "old.name",
        "full_name": "Học sinh A",
        "class_name": "10A1",
        "role": "student",
    }

    first = scan_registered_users([user])
    assert first["violation_count"] == 1
    assert first["violations"][0]["suggestions"] == []
    # "old.name" van hop le, chi con loai 10A1 la sai.
    assert len(identity_violations(user)) == 1

    invalid_username = {
        **user,
        "username": "aka",
        "full_name": "Nguyễn Văn An",
        "class_name": "8/2",
    }
    third = scan_registered_users([invalid_username])
    aka_violation = next(item for item in third["violations"] if item["username"] == "aka")
    assert aka_violation["suggestions"]

    fixed = {**user, "username": "an_nguyen", "class_name": "8/2"}
    second = scan_registered_users([fixed])
    assert second["violation_count"] == 0
    assert second["violations"][0]["status"] == "resolved"


def test_rename_user_preserves_id_and_updates_parent_links(tmp_path, monkeypatch):
    users_file = tmp_path / "users.json"
    requests = [
        {"parent_username": "parent01", "student_username": "student01", "status": "pending"}
    ]
    monkeypatch.setattr("auth_service.USERS_FILE", users_file)
    monkeypatch.setattr("auth_service._load_link_requests", lambda: requests)
    monkeypatch.setattr("auth_service._save_link_requests", lambda items: requests.__setitem__(slice(None), items))
    register_user("parent01", "Password1", "parent", "Phụ huynh")
    student = register_user("student01", "Password1", "student", "Học sinh", "8/1")

    renamed = rename_user_account("student01", "student_new", "Học sinh mới", "8/2")

    assert renamed["id"] == student["id"]
    assert renamed["username"] == "student_new"
    assert renamed["session_version"] == 1
    assert requests[0]["student_username"] == "student_new"


def test_registration_allows_invalid_identity_and_reports_only_to_owner(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr("web_app.get_username_bot_status", lambda: {"enabled": True})
    state = {"enabled": True, "violations": [], "last_scan_at": None}
    monkeypatch.setattr("username_policy.load_document", lambda *_args, **_kwargs: state.copy())

    def save_document(_key, value):
        state.update(value)

    monkeypatch.setattr("username_policy.save_document", save_document)
    monkeypatch.setenv("STUDYSYNC_SESSION_SECRET", "test-session-secret-for-invalid-identity")
    client = TestClient(app)

    registration = client.post("/api/auth/register", json={
        "username": "asdfgh",
        "password": "Password1",
        "full_name": "Nguyễn Văn An",
        "role": "student",
        "class_name": "10A1",
    })
    assert registration.status_code == 200
    assert registration.json()["user"]["username"] == "asdfgh"
    assert registration.json()["user"]["class_name"] == "10A1"
    assert state["violations"][0]["status"] == "pending"
    assert len(state["violations"][0]["reasons"]) == 2
    assert any(reason.startswith("Lớp phải") for reason in state["violations"][0]["reasons"])

    login = client.post("/api/auth/login", json={
        "username": "asdfgh",
        "password": "Password1",
    })
    assert login.status_code == 200
    assert login.json()["identity_update_required"] is False
    assert login.json()["identity_reasons"] == []

    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    profile = client.get("/api/profile", params={"username": "asdfgh"}, headers=headers)
    assert profile.status_code == 200
    assert profile.json()["user"]["class_name"] == "10A1"
    assert client.get("/api/owner/username-bot").status_code == 401


def test_legacy_user_can_use_account_and_keep_study_data(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr("owner_service.USAGE_FILE", tmp_path / "feature_usage.json")
    monkeypatch.setattr("database.study_repository.data_file", lambda name: tmp_path / name)
    monkeypatch.setattr("backend.notification_service.WEB_PUSH_SUBSCRIPTIONS_FILE", tmp_path / "tokens.json")
    monkeypatch.setattr("web_app.get_username_bot_status", lambda: {"enabled": True})
    monkeypatch.setattr("web_app.scan_registered_users", lambda _users: {})
    monkeypatch.setattr("owner_service.scan_registered_users", lambda _users: {})
    documents = {"feature_usage": [], "push_reminder_state": {}}
    monkeypatch.setattr("owner_service.load_document", lambda key, *_args, **_kwargs: documents.get(key, []))
    monkeypatch.setattr("owner_service.save_document", lambda key, value: documents.__setitem__(key, value))
    monkeypatch.setattr("feedback_service.load_document", lambda key, default, *_args, **_kwargs: default)
    monkeypatch.setattr("feedback_service.save_document", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("STUDYSYNC_SESSION_SECRET", "test-session-secret-for-identity-change")

    register_user("old.name", "Password1", "student", "Học sinh", "10A1")
    StudyBus().add_assignment("Bài giữ lại", "Toán", date(2026, 10, 1), "Cao", "old.name")
    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "old.name", "password": "Password1"})
    assert login.status_code == 200
    assert login.json()["identity_update_required"] is False
    old_headers = {"Authorization": f"Bearer {login.json()['token']}"}
    dashboard = client.get("/api/dashboard/student?username=old.name", headers=old_headers)
    assert dashboard.status_code == 200
    assert [task["title"] for task in dashboard.json()["assignments"]] == ["Bài giữ lại"]



def test_equivalent_usernames_are_treated_as_duplicate(tmp_path, monkeypatch):
    """Bỏ dấu/khoảng trắc phải ra cùng một người, không tạo được tài khoản trùng."""
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    register_user("Thanh Mai", "Password1", "student", "Thanh Mai", "8/1")

    for duplicate in ["thanh mai", "ThanhMai", "thanh_mai", "thanhmai"]:
        with pytest.raises(ValueError, match="đã tồn tại"):
            register_user(duplicate, "Password1", "student", "Khác", "8/1")


def test_login_accepts_name_with_or_without_diacritics(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    register_user("Thanh Mai", "Password1", "parent", "Thanh Mai")

    assert authenticate_user("thanh mai", "Password1") is not None
    assert authenticate_user("thanhmai", "Password1") is not None
    assert authenticate_user("THANHMAI", "Password1") is not None
    assert authenticate_user("nguoi_khac", "Password1") is None

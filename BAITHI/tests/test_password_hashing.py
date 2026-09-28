"""Kiểm tra cách lưu và kiểm tra mật khẩu.

Mật khẩu phải được lưu dạng hash, không lưu bản rõ, nhưng dữ liệu cũ đang
còn bản rõ nên phần đọc vẫn phải chấp nhận cả hai dạng để không khóa người
dùng khi triển khai.
"""
import pytest

import auth_service
from auth_service import hash_password, is_hashed_password, verify_password


def test_hash_password_is_not_plaintext():
    stored = hash_password("Quan2901")

    assert "Quan2901" not in stored
    assert is_hashed_password(stored) is True
    assert stored.startswith("pbkdf2_sha256$")


def test_hash_password_uses_random_salt():
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_password_accepts_correct_password():
    assert verify_password(hash_password("Quan2901"), "Quan2901") is True


def test_verify_password_rejects_wrong_password():
    assert verify_password(hash_password("Quan2901"), "Quan2902") is False


def test_verify_password_rejects_empty_inputs():
    assert verify_password("", "Quan2901") is False
    assert verify_password(hash_password("Quan2901"), "") is False


def test_verify_password_still_accepts_legacy_plaintext():
    """Dữ liệu cũ chưa migrate vẫn phải đăng nhập được."""
    assert is_hashed_password("student123") is False
    assert verify_password("student123", "student123") is True
    assert verify_password("student123", "student124") is False


def test_verify_password_rejects_malformed_hash():
    assert verify_password("pbkdf2_sha256$khong-hex$khong-hex", "x") is False
    assert verify_password("pbkdf2_sha256$abc", "x") is False


def test_registered_user_password_is_hashed(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_service, "USERS_FILE", tmp_path / "users.json")

    user = auth_service.register_user("hs01", "MatKhau123", "student", "Học sinh")

    assert "MatKhau123" not in user["password"]
    assert is_hashed_password(user["password"]) is True


def test_login_upgrades_plaintext_password_to_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_service, "USERS_FILE", tmp_path / "users.json")
    auth_service.register_user("hs01", "MatKhau123", "student", "Học sinh")
    users = auth_service.load_users()
    for item in users:
        item["password"] = "MatKhau123"  # giả lập dữ liệu cũ
    auth_service.save_users(users)

    assert auth_service.authenticate_user("hs01", "MatKhau123") is not None

    stored = auth_service.load_users()[0]["password"]
    assert is_hashed_password(stored) is True
    assert "MatKhau123" not in stored


def test_login_with_wrong_password_does_not_upgrade(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_service, "USERS_FILE", tmp_path / "users.json")
    auth_service.register_user("hs01", "MatKhau123", "student", "Học sinh")
    users = auth_service.load_users()
    for item in users:
        item["password"] = "MatKhau123"
    auth_service.save_users(users)

    assert auth_service.authenticate_user("hs01", "SaiMatKhau") is None

    stored = auth_service.load_users()[0]["password"]
    assert stored == "MatKhau123"


def test_change_password_stores_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_service, "USERS_FILE", tmp_path / "users.json")
    auth_service.register_user("hs01", "MatKhau123", "student", "Học sinh")

    auth_service.update_account(
        "hs01", current_password="MatKhau123", new_password="MatKhauMoi456"
    )

    stored = auth_service.load_users()[0]["password"]
    assert is_hashed_password(stored) is True
    assert "MatKhauMoi456" not in stored
    assert auth_service.authenticate_user("hs01", "MatKhauMoi456") is not None
    assert auth_service.authenticate_user("hs01", "MatKhau123") is None


def test_change_password_rejects_wrong_current_password(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_service, "USERS_FILE", tmp_path / "users.json")
    auth_service.register_user("hs01", "MatKhau123", "student", "Học sinh")

    with pytest.raises(ValueError, match="Mật khẩu hiện tại không đúng"):
        auth_service.update_account(
            "hs01", current_password="KhongDung", new_password="MatKhauMoi456"
        )


def test_set_pin_accepts_hashed_password(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_service, "USERS_FILE", tmp_path / "users.json")
    auth_service.register_user("hs01", "MatKhau123", "student", "Học sinh")

    assert auth_service.set_secondary_pin("hs01", "MatKhau123", "1234") is True
    assert auth_service.verify_secondary_pin("hs01", "1234") is True


def test_set_pin_rejects_wrong_password_with_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_service, "USERS_FILE", tmp_path / "users.json")
    auth_service.register_user("hs01", "MatKhau123", "student", "Học sinh")

    with pytest.raises(ValueError, match="Mật khẩu hiện tại không đúng"):
        auth_service.set_secondary_pin("hs01", "SaiMatKhau", "1234")


def test_locked_account_cannot_login(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_service, "USERS_FILE", tmp_path / "users.json")
    auth_service.register_user("hs01", "MatKhau123", "student", "Học sinh")
    auth_service.update_account("hs01", is_active=False, by_owner=True)

    assert auth_service.authenticate_user("hs01", "MatKhau123") is None

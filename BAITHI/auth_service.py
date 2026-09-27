from __future__ import annotations

import json
import hashlib
import hmac
import secrets
from datetime import datetime
from threading import RLock
from uuid import uuid4
from typing import Any

from data_storage import data_file, write_json_atomic

USERS_FILE = data_file("users.json")
LINK_REQUESTS_FILE = data_file("link_requests.json")
USERS_LOCK = RLock()
LINK_REQUESTS_LOCK = RLock()


def _ensure_store() -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        write_json_atomic(USERS_FILE, {"users": []})


def _ensure_link_request_store() -> None:
    LINK_REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not LINK_REQUESTS_FILE.exists():
        write_json_atomic(LINK_REQUESTS_FILE, [])


def _load_link_requests() -> list[dict[str, Any]]:
    _ensure_link_request_store()
    try:
        requests = json.loads(LINK_REQUESTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Không đọc được dữ liệu liên kết tại {LINK_REQUESTS_FILE}.") from exc
    if not isinstance(requests, list):
        raise RuntimeError(f"Dữ liệu liên kết tại {LINK_REQUESTS_FILE} không hợp lệ.")
    return requests


def _save_link_requests(requests: list[dict[str, Any]]) -> None:
    _ensure_link_request_store()
    write_json_atomic(LINK_REQUESTS_FILE, requests)


def load_users() -> list[dict[str, Any]]:
    with USERS_LOCK:
        _ensure_store()
        try:
            data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Không đọc được dữ liệu tài khoản tại {USERS_FILE}.") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"Dữ liệu tài khoản tại {USERS_FILE} không hợp lệ.")
        users = data.get("users", [])
        if not isinstance(users, list):
            raise RuntimeError(f"Danh sách tài khoản tại {USERS_FILE} không hợp lệ.")

        used_codes = {
            str(user.get("student_id", "")).strip().upper()
            for user in users
            if user.get("role") == "student" and str(user.get("student_id", "")).strip()
        }
        changed = False
        next_number = 1
        for user in users:
            if user.get("role") != "student" or str(user.get("student_id", "")).strip():
                continue
            while f"HS-{next_number:03d}" in used_codes:
                next_number += 1
            user["student_id"] = f"HS-{next_number:03d}"
            used_codes.add(user["student_id"])
            next_number += 1
            changed = True
        if changed:
            save_users(users)
        return users


def save_users(users: list[dict[str, Any]]) -> None:
    _ensure_store()
    write_json_atomic(USERS_FILE, {"users": users})


def get_user_by_username(username: str) -> dict[str, Any] | None:
    user_name = (username or "").strip()
    if not user_name:
        return None
    for user in load_users():
        if str(user.get("username", "")).strip().lower() == user_name.lower():
            return user
    return None


def list_users_by_role(role: str) -> list[dict[str, Any]]:
    target_role = (role or "student").strip().lower()
    return [user for user in load_users() if str(user.get("role", "student")).strip().lower() == target_role]


def get_student_by_id(student_id: str) -> dict[str, Any] | None:
    code = (student_id or "").strip().lower()
    if not code:
        return None
    for user in list_users_by_role("student"):
        if str(user.get("student_id", "")).strip().lower() == code:
            return user
    return None


def get_students_for_parent(parent_username: str) -> list[dict[str, Any]]:
    parent_user = get_user_by_username(parent_username)
    if not parent_user or parent_user.get("role") != "parent":
        return []

    linked_student_ids = [
        str(item.get("student_id", "")).strip()
        for item in load_users()
        if str(item.get("parent_username", "")).strip().lower() == str(parent_username).strip().lower()
    ]

    filtered = []
    for user in load_users():
        if user.get("role") != "student":
            continue
        if str(user.get("student_id", "")).strip() in linked_student_ids:
            filtered.append(user)
    return filtered


def assign_student_to_parent(parent_username: str, student_username: str) -> dict[str, Any]:
    parent = get_user_by_username(parent_username)
    student = get_user_by_username(student_username)
    if not parent or parent.get("role") != "parent":
        raise ValueError("Tài khoản phụ huynh không hợp lệ.")
    if not student or student.get("role") != "student":
        raise ValueError("Tài khoản học sinh không hợp lệ.")

    with USERS_LOCK:
        users = load_users()
        for item in users:
            if str(item.get("username", "")).strip().lower() == str(student_username).strip().lower():
                item["parent_username"] = str(parent_username).strip()
                item["student_id"] = item.get("student_id") or f"HS-{len(users):04d}"
                break
        save_users(users)
    return student


def assign_student_id_to_parent(parent_username: str, student_id: str) -> dict[str, Any]:
    student = get_student_by_id(student_id)
    if not student:
        raise ValueError("Không tìm thấy mã học sinh.")
    return assign_student_to_parent(parent_username, str(student["username"]))


def create_parent_link_request(parent_username: str, student_id: str) -> dict[str, Any]:
    parent = get_user_by_username(parent_username)
    student = get_student_by_id(student_id)
    if not parent or parent.get("role") != "parent":
        raise ValueError("Tài khoản phụ huynh không hợp lệ.")
    if not student:
        raise ValueError("Không tìm thấy mã học sinh.")
    if str(student.get("parent_username", "")).strip():
        raise ValueError("Học sinh này đã được liên kết với một tài khoản phụ huynh.")

    with LINK_REQUESTS_LOCK:
        requests = _load_link_requests()
        for item in requests:
            if (
                item.get("status") == "pending"
                and str(item.get("parent_username", "")).lower() == parent_username.strip().lower()
                and str(item.get("student_id", "")).lower() == student_id.strip().lower()
            ):
                return item

        item = {
            "id": f"link-{uuid4().hex[:12]}",
            "parent_username": parent_username.strip(),
            "parent_name": parent.get("full_name") or parent_username.strip(),
            "student_username": student.get("username", ""),
            "student_id": student.get("student_id", student_id.strip()),
            "status": "pending",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "responded_at": "",
        }
        requests.append(item)
        _save_link_requests(requests)
        return item


def get_link_requests_for_student(student_username: str) -> list[dict[str, Any]]:
    return [
        item for item in _load_link_requests()
        if str(item.get("student_username", "")).lower() == student_username.strip().lower()
    ]


def respond_to_parent_link_request(student_username: str, request_id: str, accept: bool) -> dict[str, Any]:
    with LINK_REQUESTS_LOCK:
        requests = _load_link_requests()
        target = next(
        (
            item for item in requests
            if item.get("id") == request_id
            and str(item.get("student_username", "")).lower() == student_username.strip().lower()
            and item.get("status") == "pending"
        ),
            None,
        )
        if not target:
            raise ValueError("Không tìm thấy yêu cầu liên kết đang chờ xử lý.")

        if accept:
            student = get_user_by_username(student_username)
            if not student:
                raise ValueError("Không tìm thấy tài khoản học sinh.")
            if str(student.get("parent_username", "")).strip():
                raise ValueError("Tài khoản học sinh đã có phụ huynh liên kết.")
            with USERS_LOCK:
                users = load_users()
                for user in users:
                    if str(user.get("username", "")).lower() == student_username.strip().lower():
                        user["parent_username"] = target["parent_username"]
                        break
                save_users(users)

        target["status"] = "accepted" if accept else "rejected"
        target["responded_at"] = datetime.now().isoformat(timespec="seconds")
        _save_link_requests(requests)
        return target


def update_linked_student(
    parent_username: str,
    student_id: str,
    full_name: str,
    class_name: str,
    avatar: str,
    is_active: bool,
) -> dict[str, Any]:
    linked = get_students_for_parent(parent_username)
    if not any(str(item.get("student_id", "")).strip().lower() == str(student_id).strip().lower() for item in linked):
        raise ValueError("Học sinh chưa được liên kết với tài khoản phụ huynh này.")
    with USERS_LOCK:
        users = load_users()
        for item in users:
            if str(item.get("student_id", "")).strip().lower() == str(student_id).strip().lower():
                clean_name = (full_name or "").strip()
                if not clean_name:
                    raise ValueError("Tên học sinh không được để trống.")
                item.update({
                    "full_name": clean_name,
                    "class_name": (class_name or "").strip(),
                    "avatar": (avatar or "").strip(),
                    "is_active": bool(is_active),
                })
                save_users(users)
                return item
    raise ValueError("Không tìm thấy học sinh.")


def register_user(
    username: str,
    password: str,
    role: str,
    full_name: str = "",
    class_name: str = "",
    student_id: str = "",
    parent_username: str | None = None,
) -> dict[str, Any]:
    clean_username = (username or "").strip()
    clean_password = (password or "").strip()
    clean_role = (role or "student").strip().lower()
    clean_full_name = (full_name or "").strip()
    clean_class = (class_name or "").strip()
    clean_parent_username = (parent_username or "").strip()

    if not clean_username:
        raise ValueError("Tên đăng nhập không được để trống.")
    if len(clean_password) < 6:
        raise ValueError("Mật khẩu phải có ít nhất 6 ký tự.")
    if clean_role not in {"student", "parent"}:
        clean_role = "student"

    with USERS_LOCK:
        users = load_users()
        if any(str(item.get("username", "")).strip().lower() == clean_username.lower() for item in users):
            raise ValueError("Tên đăng nhập đã tồn tại.")

        if clean_role == "student" and not str(student_id).strip():
            student_count = sum(1 for item in users if item.get("role") == "student")
            student_id = f"HS-{student_count + 1:03d}"
        user = {
            "id": f"user-{uuid4().hex}",
            "username": clean_username,
            "password": clean_password,
            "role": clean_role,
            "full_name": clean_full_name or clean_username,
            "class_name": clean_class,
            "student_id": student_id,
            "parent_username": clean_parent_username,
            "avatar": "",
            "is_active": True,
            "pin_login_enabled": False,
        }
        users.append(user)
        save_users(users)
        return user


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_username(username)
    if not user:
        return None
    if str(user.get("password", "")) != str(password):
        return None
    if not user.get("is_active", True):
        return None
    return user


def set_secondary_pin(username: str, password: str, pin: str) -> bool:
    clean_pin = str(pin or "").strip()
    if not clean_pin.isdigit() or not 4 <= len(clean_pin) <= 8:
        raise ValueError("Mã PIN phải gồm từ 4 đến 8 chữ số.")

    with USERS_LOCK:
        users = load_users()
        for user in users:
            if str(user.get("username", "")).strip().lower() != str(username or "").strip().lower():
                continue
            if str(user.get("password", "")) != str(password or ""):
                raise ValueError("Mật khẩu hiện tại không đúng.")
            salt = secrets.token_bytes(16)
            pin_hash = hashlib.pbkdf2_hmac("sha256", clean_pin.encode("utf-8"), salt, 200_000)
            user["secondary_pin_salt"] = salt.hex()
            user["secondary_pin_hash"] = pin_hash.hex()
            user["pin_login_enabled"] = True
            save_users(users)
            return True
    raise ValueError("Không tìm thấy tài khoản.")


def verify_secondary_pin(username: str, pin: str) -> bool:
    user = get_user_by_username(username)
    if not user:
        return False
    try:
        salt = bytes.fromhex(str(user.get("secondary_pin_salt", "")))
        expected_hash = bytes.fromhex(str(user.get("secondary_pin_hash", "")))
        actual_hash = hashlib.pbkdf2_hmac(
            "sha256", str(pin or "").strip().encode("utf-8"), salt, 200_000
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual_hash, expected_hash)


def set_pin_login_enabled(username: str, password: str, enabled: bool, pin: str = "") -> bool:
    with USERS_LOCK:
        users = load_users()
        for user in users:
            if str(user.get("username", "")).strip().lower() != str(username or "").strip().lower():
                continue
            if str(user.get("password", "")) != str(password or ""):
                raise ValueError("Mật khẩu hiện tại không đúng.")
            has_pin = bool(user.get("secondary_pin_hash") and user.get("secondary_pin_salt"))
            if enabled and not has_pin:
                raise ValueError("Hãy đăng ký mã PIN trước khi bật bảo vệ đăng nhập.")
            if not enabled and has_pin and not verify_secondary_pin(username, pin):
                raise ValueError("PIN hiện tại không đúng.")
            user["pin_login_enabled"] = bool(enabled)
            save_users(users)
            return True
    raise ValueError("Không tìm thấy tài khoản.")

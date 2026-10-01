from __future__ import annotations

import json
import hashlib
import hmac
import re
import secrets
from datetime import datetime
from threading import RLock
from uuid import uuid4
from typing import Any

from data_storage import data_file, write_json_atomic

from db import load_document, save_document

USERS_FILE = data_file("users.json")
LINK_REQUESTS_FILE = data_file("link_requests.json")
USERS_LOCK = RLock()
LINK_REQUESTS_LOCK = RLock()

# Mat khau duoc luu duoi dang hash PBKDF2, khong luu ban ro.
# Dung PBKDF2 de doi xung voi cach luu PIN, khong them thu vien ngoai.
PASSWORD_ITERATIONS = 200_000
_PASSWORD_PREFIX = "pbkdf2_sha256$"
_STUDENT_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_student_id(used_codes: set[str]) -> str:
    normalized_codes = {str(code).strip().upper() for code in used_codes}
    while True:
        suffix = "".join(secrets.choice(_STUDENT_CODE_ALPHABET) for _ in range(8))
        student_id = f"HS-{suffix}"
        if student_id not in normalized_codes:
            return student_id


def hash_password(password: str) -> str:
    """Tra ve chuoi 'pbkdf2_sha256$<salt_hex>$<hash_hex>'."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", str(password or "").encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"{_PASSWORD_PREFIX}{salt.hex()}${digest.hex()}"


def is_hashed_password(value: str) -> bool:
    return str(value or "").startswith(_PASSWORD_PREFIX)


def verify_password(stored: str, candidate: str) -> bool:
    """So sanh mat khau nhap voi gia tri da luu (hash hoac van con ban ro)."""
    text = str(stored or "")
    if not text:
        return False
    if not is_hashed_password(text):
        # Truong hop du lieu cu chua duoc migrate: van so sanh truc tiep.
        return hmac.compare_digest(text, str(candidate or ""))
    try:
        _, salt_hex, digest_hex = text.split("$", 2)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256", str(candidate or "").encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return hmac.compare_digest(actual, expected)


def _ensure_store() -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        write_json_atomic(USERS_FILE, {"users": []})


def _ensure_link_request_store() -> None:
    LINK_REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not LINK_REQUESTS_FILE.exists():
        write_json_atomic(LINK_REQUESTS_FILE, [])


def _load_link_requests() -> list[dict[str, Any]]:
    requests = load_document("link_requests", [], "liên kết")
    if not isinstance(requests, list):
        raise RuntimeError("Dữ liệu liên kết không hợp lệ.")
    return requests


def _save_link_requests(requests: list[dict[str, Any]]) -> None:
    save_document("link_requests", requests)


def load_users() -> list[dict[str, Any]]:
    with USERS_LOCK:
        data = load_document("users", {"users": []}, "tài khoản")
        if not isinstance(data, dict):
            raise RuntimeError("Dữ liệu tài khoản không hợp lệ.")
        users = data.get("users", [])
        if not isinstance(users, list):
            raise RuntimeError("Danh sách tài khoản không hợp lệ.")

        used_codes: set[str] = set()
        changed = False
        for user in users:
            if user.get("role") != "student":
                continue
            student_id = str(user.get("student_id", "")).strip()
            normalized_id = student_id.upper()
            if not student_id or normalized_id in used_codes:
                student_id = _generate_student_id(used_codes)
                user["student_id"] = student_id
                normalized_id = student_id.upper()
                changed = True
            used_codes.add(normalized_id)
        if changed:
            save_users(users)
        return users


def save_users(users: list[dict[str, Any]]) -> None:
    save_document("users", {"users": users})


def delete_user_account(username: str) -> bool:
    target = str(username or "").strip().casefold()
    if not target:
        return False
    with USERS_LOCK:
        users = load_users()
        remaining = [
            user for user in users
            if str(user.get("username", "")).strip().casefold() != target
        ]
        if len(remaining) == len(users):
            return False
        for user in remaining:
            if str(user.get("parent_username", "")).strip().casefold() == target:
                user.pop("parent_username", None)
        save_users(remaining)

    with LINK_REQUESTS_LOCK:
        requests = _load_link_requests()
        remaining_requests = [
            item for item in requests
            if str(item.get("parent_username", "")).strip().casefold() != target
            and str(item.get("student_username", "")).strip().casefold() != target
        ]
        if len(remaining_requests) != len(requests):
            _save_link_requests(remaining_requests)
    return True


def rename_user_account(current_username: str, new_username: str, full_name: str, class_name: str) -> dict[str, Any]:
    old_name = str(current_username or "").strip()
    next_name = str(new_username or "").strip()
    if not old_name or not next_name:
        raise ValueError("Tên đăng nhập không được để trống.")
    with USERS_LOCK:
        users = load_users()
        current = next(
            (user for user in users if usernames_match(str(user.get("username", "")), old_name)),
            None,
        )
        if current is None:
            raise ValueError("Không tìm thấy tài khoản.")
        if any(
            usernames_match(str(user.get("username", "")), next_name) and user is not current
            for user in users
        ):
            raise ValueError("Tên đăng nhập đã tồn tại.")
        for user in users:
            if str(user.get("parent_username", "")).casefold() == old_name.casefold():
                user["parent_username"] = next_name
        current["username"] = next_name
        current["full_name"] = full_name.strip()
        if str(current.get("role")) == "student":
            current["class_name"] = class_name.strip()
        current["session_version"] = int(current.get("session_version", 0)) + 1
        save_users(users)
        updated_user = dict(current)

    with LINK_REQUESTS_LOCK:
        requests = _load_link_requests()
        changed = False
        for item in requests:
            for key in ("parent_username", "student_username"):
                if str(item.get(key, "")).casefold() == old_name.casefold():
                    item[key] = next_name
                    changed = True
        if changed:
            _save_link_requests(requests)
    return updated_user


def get_user_by_username(username: str) -> dict[str, Any] | None:
    user_name = (username or "").strip()
    if not user_name:
        return None
    for user in load_users():
        if usernames_match(str(user.get("username", "")), user_name):
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
                if not str(item.get("student_id", "")).strip():
                    used_codes = {
                        str(user.get("student_id", "")).strip().upper()
                        for user in users
                        if user.get("role") == "student"
                    }
                    item["student_id"] = _generate_student_id(used_codes)
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


def normalize_username(value: str) -> str:
    """Bỏ dấu, bỏ khoảng trắng, gạch dưới và dấu chấm; hạ chữ thường.

    Dùng để so sánh tên đăng nhập: "Thanh Mai", "thanhmai" và "thanh_mai"
    phải được xem là cùng một người, tránh tạo tài khoản trùng.
    """
    import unicodedata

    text = re.sub(r"[_\s.]", "", str(value or ""))
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def usernames_match(left: str, right: str) -> bool:
    return normalize_username(left) == normalize_username(right)


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
        if any(usernames_match(str(item.get("username", "")), clean_username) for item in users):
            raise ValueError("Tên đăng nhập đã tồn tại.")

        if clean_role == "student":
            used_codes = {
                str(item.get("student_id", "")).strip().upper()
                for item in users
                if item.get("role") == "student"
            }
            if not str(student_id).strip() or str(student_id).strip().upper() in used_codes:
                student_id = _generate_student_id(used_codes)
        user = {
            "id": f"user-{uuid4().hex}",
            "username": clean_username,
            "password": hash_password(clean_password),
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
    if not verify_password(user.get("password", ""), password):
        return None
    if not user.get("is_active", True):
        return None
    # Nâng du liệu lên hash ngay lan dang nhap thanh cong, thay vi ghi script migrate.
    if not is_hashed_password(user.get("password", "")):
        with USERS_LOCK:
            current = load_users()
            for item in current:
                if str(item.get("username", "")).strip().lower() == str(username).strip().lower():
                    item["password"] = hash_password(password)
                    save_users(current)
                    user = item
                    break
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
            if not verify_password(user.get("password", ""), password or ""):
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
            if not verify_password(user.get("password", ""), password or ""):
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


def update_account(username: str, *, full_name: str | None = None,
                   class_name: str | None = None, avatar: str | None = None,
                   current_password: str | None = None, new_password: str | None = None,
                   is_active: bool | None = None, by_owner: bool = False) -> dict[str, Any]:
    # Do not allow changes to username, role or student ID."
    if new_password is not None and len(new_password) < 6:
        raise ValueError("Mật khẩu mới phải có ít nhất 6 ký tự.")
    if full_name is not None and (not full_name.strip() or len(full_name.strip()) > 100):
        raise ValueError("Họ tên phải có từ 1 đến 100 ký tự.")
    if class_name is not None and len(class_name.strip()) > 50:
        raise ValueError("Tên lớp quá dài.")
    if avatar is not None and len(avatar.strip()) > 100:
        raise ValueError("Avatar quá dài.")
    with USERS_LOCK:
        users = load_users()
        for user in users:
            if str(user.get("username", "")).lower() != username.strip().lower():
                continue
            if not by_owner and not user.get("is_active", True):
                raise ValueError("Tài khoản đã bị khóa.")
            if new_password is not None and not by_owner and not verify_password(
                user.get("password", ""), current_password or ""
            ):
                raise ValueError("Mật khẩu hiện tại không đúng.")
            if full_name is not None:
                user["full_name"] = full_name.strip()
            if class_name is not None:
                user["class_name"] = class_name.strip()
            if avatar is not None:
                user["avatar"] = avatar.strip()
            if is_active is not None and by_owner:
                user["is_active"] = is_active
                if not is_active:
                    user["session_version"] = int(user.get("session_version", 0)) + 1
            if new_password is not None:
                user["password"] = hash_password(new_password)
                user["session_version"] = int(user.get("session_version", 0)) + 1
            save_users(users)
            return user
    raise ValueError("Không tìm thấy tài khoản.")

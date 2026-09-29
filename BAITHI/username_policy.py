from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from db import load_document, save_document

POLICY_DOCUMENT = "username_policy"
MIN_USERNAME_LENGTH = 6
MAX_USERNAME_LENGTH = 20
VALID_CLASS_PATTERN = re.compile(r"^([6-9])\s*/\s*([1-3])$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{5,19}$")
RESERVED_USERNAMES = {
    "admin",
    "administrator",
    "mod",
    "moderator",
    "teacher",
    "studysync",
    "studysyncofficial",
    "studysync_official",
    "support",
    "system",
}
DISALLOWED_TERMS = {
    "dâm",
    "địt",
    "đĩ",
    "lồn",
    "phò",
    "xxx",
}
SPAM_USERNAMES = {
    "asdfgh",
    "asdfjkl",
    "qwerty",
    "qwertyui",
    "zxcvbn",
    "abcdef",
    "abc123",
    "123456",
    "1234567",
}


def _fold_vietnamese(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char)).replace("đ", "d")


def _contains_disallowed_term(value: str) -> bool:
    words = set(re.findall(r"[a-z]+", _fold_vietnamese(value)))
    return bool(words.intersection(_fold_vietnamese(term) for term in DISALLOWED_TERMS))


def validate_username(username: str) -> tuple[bool, str]:
    value = str(username or "").strip()
    # Kiem tra ten danh cho he thong truoc, neu biet truoc se bao loi chinh xac
    # thay vi bao nhieu ky tu (vi du "admin" bi bao sai la quá ngan).
    folded_for_reserved = _fold_vietnamese(value).replace("_", "")
    if (
        value.casefold() in RESERVED_USERNAMES
        or folded_for_reserved in RESERVED_USERNAMES
        or any(folded_for_reserved.startswith(name) for name in ("admin", "mod", "teacher", "support", "system"))
    ):
        return False, "Tên đăng nhập này dành riêng cho hệ thống."
    if not MIN_USERNAME_LENGTH <= len(value) <= MAX_USERNAME_LENGTH:
        return False, "Tên đăng nhập phải dài từ 6 đến 20 ký tự."
    if not USERNAME_PATTERN.fullmatch(value):
        return False, "Tên đăng nhập chỉ dùng chữ không dấu, số và dấu gạch dưới; phải bắt đầu bằng chữ cái."

    compact = value.casefold().replace("_", "")
    if value.casefold() in SPAM_USERNAMES or any(spam in compact for spam in SPAM_USERNAMES):
        return False, "Tên đăng nhập quá phổ biến hoặc có dạng gõ bừa."
    if len(set(value.casefold())) == 1 or re.search(r"(.)\1{5,}", value.casefold()):
        return False, "Không được dùng một ký tự lặp lại làm tên đăng nhập."
    if _contains_disallowed_term(value):
        return False, "Tên đăng nhập có từ ngữ không phù hợp môi trường học đường."
    return True, ""


def validate_class_name(class_name: str) -> tuple[bool, str]:
    value = str(class_name or "").strip()
    match = VALID_CLASS_PATTERN.fullmatch(value)
    if not match:
        return False, "Lớp phải theo dạng khối 6–9, ví dụ 6/1, 7/2, 8/3 hoặc 9/1."
    return True, f"{match.group(1)}/{match.group(2)}"


def validate_display_name(full_name: str) -> tuple[bool, str]:
    value = str(full_name or "").strip()
    if not value or len(value) > 100:
        return False, "Họ tên phải có từ 1 đến 100 ký tự."
    if _contains_disallowed_term(value):
        return False, "Họ tên có từ ngữ không phù hợp môi trường học đường."
    if re.search(r"https?://|www\.|@|[0-9]{4,}", value, re.IGNORECASE):
        return False, "Hãy nhập họ tên thật, không dùng liên kết, email hoặc chuỗi số."
    return True, ""


def generate_suggested_username(
    full_name: str,
    birth_year: int | None = None,
    existing_usernames: list[str] | None = None,
) -> list[str]:
    name = _fold_vietnamese(str(full_name or ""))
    words = re.findall(r"[a-z]+", name)
    if not words:
        return []
    year = str(birth_year) if birth_year and 1900 <= birth_year <= datetime.now().year else ""
    year_two_digits = year[-2:] if year else ""

    if len(words) == 1:
        # Chi co mot tu: khong tao duoc ten "hihi_hihi" vo nghia.
        only = words[0]
        candidates = [
            f"{only}{year}",
            f"{only}{year_two_digits}",
            only,
            f"{only}_sv",
        ]
    else:
        first_name = words[-1]
        family_name = words[0]
        candidates = [
            f"{first_name}_{family_name}{year}",
            f"{first_name}_{family_name}{year_two_digits}",
            f"{''.join(words)}{year_two_digits}",
            f"{first_name}_{family_name}",
        ]

    suggestions: list[str] = []
    used = {str(item).casefold() for item in (existing_usernames or [])}
    base_candidate = ""
    for candidate in candidates:
        candidate = candidate[:MAX_USERNAME_LENGTH]
        is_valid, _ = validate_username(candidate)
        if is_valid and not base_candidate:
            base_candidate = candidate
        if is_valid and candidate.casefold() not in used and candidate not in suggestions:
            suggestions.append(candidate)
    if base_candidate and len(suggestions) < 4:
        for suffix in range(2, 100):
            candidate = f"{base_candidate[:MAX_USERNAME_LENGTH - len(str(suffix)) - 1]}_{suffix}"
            is_valid, _ = validate_username(candidate)
            if is_valid and candidate.casefold() not in used and candidate not in suggestions:
                suggestions.append(candidate)
            if len(suggestions) >= 4:
                break
    return suggestions


def _suggest_class(user: dict[str, Any]) -> str:
    """Goi y lop 6-9 khi lop hien tai khong hop le (vd "lop 5" -> "6/1")."""
    if str(user.get("role", "student")) != "student":
        return ""
    current = str(user.get("class_name", "")).strip()
    if validate_class_name(current)[0]:
        return current
    numbers = re.findall(r"\d+", current)
    grade = numbers[0] if numbers else ""
    if grade not in {"6", "7", "8", "9"}:
        grade = "6"
    return f"{grade}/1"


def identity_violations(user: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    valid_username, username_message = validate_username(str(user.get("username", "")))
    if not valid_username:
        reasons.append(username_message)
    if str(user.get("role", "student")) == "student":
        valid_name, name_message = validate_display_name(str(user.get("full_name", "")))
        if not valid_name:
            reasons.append(name_message)
        valid_class, class_message = validate_class_name(str(user.get("class_name", "")))
        if not valid_class:
            reasons.append(class_message)
    return reasons


def _read_state() -> dict[str, Any]:
    state = load_document(POLICY_DOCUMENT, {"enabled": True, "violations": [], "last_scan_at": None}, "kiểm duyệt tài khoản")
    if not isinstance(state, dict):
        raise RuntimeError("Trạng thái kiểm duyệt tài khoản không hợp lệ.")
    violations = state.get("violations", [])
    if not isinstance(violations, list):
        raise RuntimeError("Danh sách cảnh báo username không hợp lệ.")
    return {
        "enabled": bool(state.get("enabled", True)),
        "violations": violations,
        "last_scan_at": state.get("last_scan_at"),
    }


def get_username_bot_status() -> dict[str, Any]:
    state = _read_state()
    return {
        "enabled": state["enabled"],
        "last_scan_at": state["last_scan_at"],
        "violations": state["violations"],
        "violation_count": sum(1 for item in state["violations"] if item.get("status") == "pending"),
    }


def set_username_bot_enabled(enabled: bool) -> dict[str, Any]:
    state = _read_state()
    state["enabled"] = bool(enabled)
    save_document(POLICY_DOCUMENT, state)
    return get_username_bot_status()


def resolve_username_violation(username: str) -> bool:
    target = str(username or "").strip().casefold()
    if not target:
        return False
    state = _read_state()
    changed = False
    for item in state["violations"]:
        if str(item.get("username", "")).strip().casefold() == target and item.get("status") == "pending":
            item["status"] = "reviewed"
            changed = True
    if changed:
        save_document(POLICY_DOCUMENT, state)
    return changed


def record_signup_violation(username: str, reasons: list[str]) -> None:
    state = _read_state()
    if not state["enabled"] or not reasons:
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["violations"].append({
        "username": str(username or "").strip()[:80],
        "role": "registration",
        "reasons": reasons,
        "status": "pending",
        "first_seen_at": now,
        "last_seen_at": now,
    })
    state["violations"] = state["violations"][-200:]
    save_document(POLICY_DOCUMENT, state)


def resolve_signup_violation(username: str) -> None:
    target = str(username or "").strip().casefold()
    if not target:
        return
    state = _read_state()
    changed = False
    for item in state["violations"]:
        if (
            item.get("role") == "registration"
            and str(item.get("username", "")).strip().casefold() == target
            and item.get("status") == "pending"
        ):
            item["status"] = "resolved"
            changed = True
    if changed:
        save_document(POLICY_DOCUMENT, state)


def scan_registered_users(users: list[dict[str, Any]]) -> dict[str, Any]:
    state = _read_state()
    if not state["enabled"]:
        return get_username_bot_status()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    existing = {
        str(item.get("username", "")).casefold(): item
        for item in state["violations"]
        if item.get("role") != "registration"
    }
    seen_keys: set[str] = set()
    all_usernames = [str(item.get("username", "")) for item in users]
    for user in users:
        username = str(user.get("username", "")).strip()
        key = username.casefold()
        seen_keys.add(key)
        reasons = identity_violations(user)
        if not reasons:
            if key in existing:
                existing[key]["status"] = "resolved"
                existing[key]["last_seen_at"] = now
            continue
        old = existing.get(key, {})
        existing[key] = {
            "username": username,
            "role": str(user.get("role", "student")),
            "reasons": reasons,
            # Kem goi y de quan tri co the doi nhanh trong trang admin.
            "suggestions": generate_suggested_username(
                str(user.get("full_name", "")), existing_usernames=all_usernames
            ),
            "suggested_class": _suggest_class(user),
            "status": "pending",
            "first_seen_at": old.get("first_seen_at", now),
            "last_seen_at": now,
        }

    for key, item in existing.items():
        if key not in seen_keys and item.get("status") == "pending":
            item["status"] = "resolved"
            item["last_seen_at"] = now

    account_violations = list(existing.values())
    state["violations"] = (account_violations + [
        item for item in state["violations"] if item.get("role") == "registration"
    ])[-200:]
    state["last_scan_at"] = now
    save_document(POLICY_DOCUMENT, state)
    return get_username_bot_status()

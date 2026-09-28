from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from auth_service import delete_user_account, get_user_by_username, load_users, update_account
from backend.notification_service import remove_user_web_tokens
from bus.study_bus import StudyBus
from data_storage import data_file
from db import load_document, save_document


USAGE_FILE = data_file("feature_usage.json")
USAGE_LOCK = RLock()


def record_successful_feature_use(username: str, feature: str) -> None:
    clean_username = str(username or "").strip()
    clean_feature = str(feature or "").strip()
    if not clean_username or not clean_feature:
        return

    with USAGE_LOCK:
        events = _read_usage_events()
        events.append({
            "id": uuid4().hex,
            "username": clean_username,
            "feature": clean_feature,
            "used_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        save_document("feature_usage", events)


def _read_usage_events() -> list[dict[str, Any]]:
    events = load_document("feature_usage", [], "thống kê sử dụng tính năng")
    if not isinstance(events, list):
        raise RuntimeError("Dữ liệu thống kê sử dụng không hợp lệ.")
    return events


def get_owner_overview() -> dict[str, Any]:
    users = load_users()
    events = _read_usage_events()
    successful_usernames = {
        str(event.get("username", "")).strip().lower()
        for event in events
        if str(event.get("username", "")).strip()
    }
    feature_counts = Counter(str(event.get("feature", "")) for event in events)
    role_counts = Counter(str(user.get("role", "student")) for user in users)
    return {
        "users": {
            "total": len(users),
            "students": role_counts.get("student", 0),
            "parents": role_counts.get("parent", 0),
            "active": sum(1 for user in users if user.get("is_active", True)),
            "used_features": len(successful_usernames),
        },
        "successful_actions": len(events),
        "feature_usage": dict(feature_counts),
    }


def list_managed_users() -> list[dict[str, Any]]:
    events = _read_usage_events()
    use_by_username: dict[str, list[str]] = {}
    for event in events:
        username = str(event.get("username", "")).strip().lower()
        feature = str(event.get("feature", "")).strip()
        if username and feature:
            use_by_username.setdefault(username, []).append(feature)

    users = load_users()
    return [
        {
            "id": str(user.get("id", "")),
            "username": str(user.get("username", "")),
            "full_name": str(user.get("full_name", "")),
            "role": str(user.get("role", "student")),
            "class_name": str(user.get("class_name", "")),
            "student_id": str(user.get("student_id", "")),
            "is_active": bool(user.get("is_active", True)),
            "successful_actions": len(use_by_username.get(str(user.get("username", "")).lower(), [])),
            "used_features": sorted(set(use_by_username.get(str(user.get("username", "")).lower(), []))),
        }
        for user in users
    ]


def managed_user_by_id(user_id: str) -> dict[str, Any] | None:
    return next((user for user in load_users() if str(user.get("id", "")) == user_id), None)


def set_managed_user_active(user_id: str, is_active: bool) -> bool:
    user = managed_user_by_id(user_id)
    if not user:
        return False
    update_account(user["username"], is_active=is_active, by_owner=True)
    return True


def delete_managed_user(user_id: str) -> bool:
    user = managed_user_by_id(user_id)
    if not user:
        return False
    username = str(user.get("username", "")).strip()
    if not delete_user_account(username):
        return False
    StudyBus().repository.delete_user_data(username)
    remove_user_web_tokens(username)
    target = username.casefold()
    with USAGE_LOCK:
        events = _read_usage_events()
        remaining_events = [
            event for event in events
            if str(event.get("username", "")).strip().casefold() != target
        ]
        if len(remaining_events) != len(events):
            save_document("feature_usage", remaining_events)
    return True
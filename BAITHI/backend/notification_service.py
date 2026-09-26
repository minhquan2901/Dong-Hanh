from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import firebase_admin
import requests
from dotenv import load_dotenv
from firebase_admin import credentials, messaging

from bus.study_bus import StudyBus

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEVICE_TOKEN_FILE = ROOT / "data" / "device_tokens.json"
WEB_TOKEN_FILE = ROOT / "data" / "web_tokens.json"
MOBILE_TOKEN_FILE = ROOT / "data" / "mobile_tokens.json"
EMAIL_PREFERENCES_FILE = ROOT / "data" / "email_preferences.json"
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
FCM_ENABLED = os.getenv("FCM_ENABLED", "false").strip().lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@studysync.local")

if GOOGLE_APPLICATION_CREDENTIALS:
    cert_path = ROOT / GOOGLE_APPLICATION_CREDENTIALS.strip().replace("./", "")
    if cert_path.exists():
        cred = credentials.Certificate(str(cert_path))
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID or None})


def _ensure_store(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("[]", encoding="utf-8")


def _read_tokens(path: Path) -> list[str]:
    try:
        tokens = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return tokens if isinstance(tokens, list) else []


def _write_tokens(path: Path, tokens: list[str]) -> None:
    path.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path, default: Any) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return value if value is not None else default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def register_device_token(token: str, device_type: str = "mobile") -> list[str]:
    token = token.strip()
    if not token:
        raise ValueError("Token thiết bị không được để trống.")

    target_file = WEB_TOKEN_FILE if device_type == "web" else MOBILE_TOKEN_FILE
    _ensure_store(target_file)
    tokens = _read_tokens(target_file)
    if token not in tokens:
        tokens.append(token)
        _write_tokens(target_file, tokens)

    if DEVICE_TOKEN_FILE != target_file:
        _ensure_store(DEVICE_TOKEN_FILE)
        all_tokens = _read_tokens(DEVICE_TOKEN_FILE)
        if token not in all_tokens:
            all_tokens.append(token)
            _write_tokens(DEVICE_TOKEN_FILE, all_tokens)
    return tokens


def register_web_token(token: str) -> list[str]:
    return register_device_token(token, device_type="web")


def register_mobile_token(token: str) -> list[str]:
    return register_device_token(token, device_type="mobile")


def save_email_preferences(username: str, email: str, enabled: bool = True) -> dict[str, Any]:
    _ensure_store(EMAIL_PREFERENCES_FILE)
    prefs = _read_json(EMAIL_PREFERENCES_FILE, {})
    if not isinstance(prefs, dict):
        prefs = {}
    prefs[username] = {"email": email.strip(), "enabled": bool(enabled)}
    _write_json(EMAIL_PREFERENCES_FILE, prefs)
    return prefs[username]


def get_email_preferences(username: str) -> dict[str, Any]:
    _ensure_store(EMAIL_PREFERENCES_FILE)
    prefs = _read_json(EMAIL_PREFERENCES_FILE, {})
    if not isinstance(prefs, dict):
        return {"email": "", "enabled": False}
    return prefs.get(username, {"email": "", "enabled": False})


def get_registered_tokens() -> list[str]:
    _ensure_store(DEVICE_TOKEN_FILE)
    return _read_tokens(DEVICE_TOKEN_FILE)


def get_registered_web_tokens() -> list[str]:
    _ensure_store(WEB_TOKEN_FILE)
    return _read_tokens(WEB_TOKEN_FILE)


def get_registered_mobile_tokens() -> list[str]:
    _ensure_store(MOBILE_TOKEN_FILE)
    return _read_tokens(MOBILE_TOKEN_FILE)


def send_email_notification(recipient: str, subject: str, body: str) -> dict[str, Any]:
    if not recipient.strip():
        return {"status": "skipped", "reason": "missing_recipient"}

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        return {
            "status": "simulated",
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "provider": "smtp-not-configured",
        }

    payload = {
        "to": recipient,
        "from": SMTP_FROM,
        "subject": subject,
        "text": body,
    }
    try:
        response = requests.post(
            f"{SMTP_HOST}:{SMTP_PORT}/sendmail",
            json=payload,
            timeout=10,
            auth=(SMTP_USER, SMTP_PASSWORD),
        )
        return {"status": "sent" if response.ok else "failed", "recipient": recipient, "subject": subject, "response": response.text}
    except Exception as exc:  # pragma: no cover - external integration path
        return {"status": "error", "recipient": recipient, "subject": subject, "error": str(exc)}


def _day_name_to_index(day_name: str) -> int:
    mapping = {
        "Thứ Hai": 0,
        "Thứ Ba": 1,
        "Thứ Tư": 2,
        "Thứ Năm": 3,
        "Thứ Sáu": 4,
        "Thứ Bảy": 5,
        "Chủ Nhật": 6,
    }
    return mapping.get(day_name, -1)


def _minutes_until_lesson(lesson: dict[str, Any]) -> int | None:
    today = datetime.now()
    day_name = str(lesson.get("day", ""))
    start_text = str(lesson.get("start", "00:00"))
    try:
        start_time = datetime.strptime(start_text, "%H:%M").time()
    except ValueError:
        return None

    target_day = _day_name_to_index(day_name)
    if target_day == -1:
        return None

    current_weekday = today.weekday()
    days_ahead = (target_day - current_weekday) % 7
    if days_ahead == 0:
        lesson_dt = datetime.combine(today.date(), start_time)
        if lesson_dt <= today:
            return None
    else:
        lesson_dt = datetime.combine((today.date() + timedelta(days=days_ahead)), start_time)

    return int((lesson_dt - today).total_seconds() // 60)


def build_notification_payloads() -> list[dict[str, str]]:
    study = StudyBus()
    payloads: list[dict[str, str]] = []

    for lesson in study.schedule():
        reminder_minutes = int(lesson.get("reminder_minutes", 30))
        minutes_until = _minutes_until_lesson(lesson)
        if minutes_until is None:
            continue
        if 0 <= minutes_until <= reminder_minutes:
            payloads.append(
                {
                    "title": f"Nhắc lịch: {lesson['subject']}",
                    "body": f"{lesson['day']} lúc {lesson['start']} · Phòng {lesson['room']} · còn {minutes_until} phút",
                }
            )

    for task in study.due_soon(7):
        if bool(task.get("completed")):
            continue
        due_date = task.get("due_date")
        if not due_date:
            continue
        try:
            due = datetime.fromisoformat(str(due_date)).date()
        except ValueError:
            continue
        delta_days = (due - date.today()).days
        if 0 <= delta_days <= 7:
            payloads.append(
                {
                    "title": f"Deadline: {task['title']}",
                    "body": f"{task['subject']} · hạn {due.isoformat()} · ưu tiên {task['priority']}",
                }
            )

    return payloads


def send_fcm_message(token: str, title: str, body: str) -> dict[str, Any]:
    if not FCM_ENABLED:
        return {"status": "disabled", "token": token, "title": title, "body": body}

    if not GOOGLE_APPLICATION_CREDENTIALS:
        return {"status": "missing_service_account", "token": token, "title": title, "body": body}

    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            token=token,
        )
        response = messaging.send(message)
        return {"status": "sent", "message_id": response, "token": token, "title": title, "body": body}
    except Exception as exc:  # pragma: no cover - runtime integration path
        return {"status": "error", "token": token, "title": title, "body": body, "error": str(exc)}


def send_push_notification(token: str, title: str, body: str) -> dict[str, Any]:
    if not token.strip():
        return {"status": "skipped", "reason": "missing_token"}
    return send_fcm_message(token, title, body)


def send_notifications_to_registered_devices() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    web_tokens = get_registered_web_tokens()
    mobile_tokens = get_registered_mobile_tokens()
    all_tokens = web_tokens + mobile_tokens

    for payload in build_notification_payloads():
        for token in all_tokens:
            result = send_fcm_message(token, payload["title"], payload["body"])
            results.append({
                "token": token,
                "device_type": "web" if token in web_tokens else "mobile",
                "title": payload["title"],
                "body": payload["body"],
                "result": result,
            })
    return results


def send_test_push(token: str, title: str, body: str, device_type: str = "mobile") -> dict[str, Any]:
    if device_type == "web":
        register_web_token(token)
    else:
        register_mobile_token(token)
    return send_fcm_message(token, title, body)

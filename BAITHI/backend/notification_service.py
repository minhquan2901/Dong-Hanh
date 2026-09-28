from __future__ import annotations

import json
import hashlib
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import firebase_admin
import requests
from dotenv import load_dotenv
from firebase_admin import credentials, messaging

from bus.study_bus import StudyBus
from data_storage import data_file, write_json_atomic
from db import load_document, save_document

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEVICE_TOKEN_FILE = data_file("device_tokens.json")
WEB_TOKEN_FILE = data_file("web_tokens.json")
WEB_PUSH_SUBSCRIPTIONS_FILE = data_file("web_push_subscriptions.json")
PUSH_REMINDER_STATE_FILE = data_file("push_reminder_state.json")
MOBILE_TOKEN_FILE = data_file("mobile_tokens.json")
EMAIL_PREFERENCES_FILE = data_file("email_preferences.json")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
FIREBASE_VAPID_KEY = os.getenv("FIREBASE_VAPID_KEY", "")
FCM_ENABLED = os.getenv("FCM_ENABLED", "false").strip().lower() == "true"
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:8000").rstrip("/")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@studysync.local")
STUDY_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
REMINDER_MILESTONES = (
    (timedelta(days=1), "Nhiệm vụ còn 1 ngày"),
    (timedelta(hours=1), "Nhiệm vụ còn 1 giờ"),
    (timedelta(minutes=10), "Nhiệm vụ còn 10 phút"),
    (timedelta(minutes=5), "Nhiệm vụ còn 5 phút"),
)


def _parse_assignment_due_at(value: Any) -> datetime | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    try:
        if "T" not in raw_value and " " not in raw_value:
            legacy_date = date.fromisoformat(raw_value)
            return datetime.combine(legacy_date, time(23, 59), STUDY_TIMEZONE)
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=STUDY_TIMEZONE)
    return parsed.astimezone(STUDY_TIMEZONE)

def _ensure_firebase_app() -> bool:
    try:
        firebase_admin.get_app()
        return True
    except ValueError:
        pass

    credential_data: dict[str, Any] | str | None = None
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        try:
            credential_data = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        except json.JSONDecodeError:
            return False
    elif GOOGLE_APPLICATION_CREDENTIALS:
        cert_path = ROOT / GOOGLE_APPLICATION_CREDENTIALS.strip().replace("./", "")
        if cert_path.exists():
            credential_data = str(cert_path)

    if credential_data is None:
        return False

    try:
        credential = credentials.Certificate(credential_data)
        firebase_admin.initialize_app(
            credential,
            {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else None,
        )
    except (ValueError, OSError):
        return False
    return True


def firebase_push_ready() -> bool:
    return FCM_ENABLED and bool(FIREBASE_VAPID_KEY) and _ensure_firebase_app()


def _ensure_store(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_json_atomic(path, [])


def _read_tokens(path: Path) -> list[str]:
    try:
        tokens = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Không đọc được dữ liệu token tại {path}.") from exc
    if not isinstance(tokens, list):
        raise RuntimeError(f"Dữ liệu token tại {path} không hợp lệ.")
    return tokens


def _write_tokens(path: Path, tokens: list[str]) -> None:
    write_json_atomic(path, tokens)


def _read_json(path: Path, default: Any) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Không đọc được dữ liệu JSON tại {path}.") from exc
    return value if value is not None else default


def _write_json(path: Path, value: Any) -> None:
    write_json_atomic(path, value)


def register_user_web_token(username: str, token: str) -> int:
    clean_username = str(username or "").strip()
    clean_token = str(token or "").strip()
    if not clean_username or not clean_token:
        raise ValueError("Tên tài khoản và token trình duyệt không được để trống.")

    subscriptions = _read_json(WEB_PUSH_SUBSCRIPTIONS_FILE, {})
    if not isinstance(subscriptions, dict):
        subscriptions = {}
    tokens = subscriptions.get(clean_username, [])
    if not isinstance(tokens, list):
        tokens = []
    if clean_token not in tokens:
        tokens.append(clean_token)
    subscriptions[clean_username] = tokens
    _write_json(WEB_PUSH_SUBSCRIPTIONS_FILE, subscriptions)
    return len(tokens)


def get_user_web_tokens(username: str) -> list[str]:
    subscriptions = _read_json(WEB_PUSH_SUBSCRIPTIONS_FILE, {})
    if not isinstance(subscriptions, dict):
        return []
    tokens = subscriptions.get(str(username or "").strip(), [])
    return [str(token) for token in tokens if str(token).strip()] if isinstance(tokens, list) else []


def remove_user_web_tokens(username: str) -> None:
    target = str(username or "").strip()
    if not target:
        return
    subscriptions = _read_json(WEB_PUSH_SUBSCRIPTIONS_FILE, {})
    if not isinstance(subscriptions, dict) or target not in subscriptions:
        return
    subscriptions.pop(target, None)
    _write_json(WEB_PUSH_SUBSCRIPTIONS_FILE, subscriptions)


def get_web_push_usernames() -> list[str]:
    subscriptions = _read_json(WEB_PUSH_SUBSCRIPTIONS_FILE, {})
    if not isinstance(subscriptions, dict):
        return []
    return [str(username) for username, tokens in subscriptions.items() if isinstance(tokens, list) and tokens]


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


def _build_notification_payloads_for_user(username: str) -> list[dict[str, str]]:
    owner_username = str(username or "").strip().lower()
    if not owner_username:
        return []
    study = StudyBus()
    payloads: list[dict[str, str]] = []

    for lesson in study.schedule(owner_username):
        reminder_minutes = int(lesson.get("reminder_minutes", 30))
        minutes_until = _minutes_until_lesson(lesson)
        if minutes_until is None:
            continue
        if 0 <= minutes_until <= reminder_minutes:
            payloads.append(
                {
                    "username": owner_username,
                    "title": f"Nhắc lịch: {lesson['subject']}",
                    "body": f"{lesson['day']} lúc {lesson['start']} · Phòng {lesson['room']} · còn {minutes_until} phút",
                }
            )

    for task in study.due_soon(7, owner_username):
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
                    "username": owner_username,
                    "title": f"Deadline: {task['title']}",
                    "body": f"{task['subject']} · hạn {due.isoformat()} · ưu tiên {task['priority']}",
                }
            )

    return payloads


def build_notification_payloads() -> list[dict[str, str]]:
    # The standalone preview endpoint has no user session, so it must not reveal records.
    return []


def send_fcm_message(
    token: str,
    title: str,
    body: str,
    web_link: str | None = None,
) -> dict[str, Any]:
    if not FCM_ENABLED:
        return {"status": "disabled", "title": title, "body": body}

    if not _ensure_firebase_app():
        return {"status": "missing_service_account", "title": title, "body": body}

    try:
        webpush = messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                icon=f"{PUBLIC_APP_URL}/static/studysync-icon-v2-192.png",
                badge=f"{PUBLIC_APP_URL}/static/studysync-icon-v2-72.png",
            ),
            fcm_options=messaging.WebpushFCMOptions(link=web_link or f"{PUBLIC_APP_URL}/student"),
        )
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            webpush=webpush,
            token=token,
        )
        response = messaging.send(message)
        return {"status": "sent", "message_id": response, "title": title, "body": body}
    except Exception as exc:  # pragma: no cover - runtime integration path
        return {"status": "error", "title": title, "body": body, "error": str(exc)}


def send_web_push_to_user(
    username: str,
    title: str,
    body: str,
    path: str = "/student",
) -> list[dict[str, Any]]:
    link = f"{PUBLIC_APP_URL}/{path.lstrip('/')}"
    return [
        send_fcm_message(token, title, body, web_link=link)
        for token in get_user_web_tokens(username)
    ]


def send_due_task_reminders(now: datetime | None = None) -> list[dict[str, Any]]:
    current_time = now or datetime.now(STUDY_TIMEZONE)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=STUDY_TIMEZONE)
    current_time = current_time.astimezone(STUDY_TIMEZONE)
    study = StudyBus()
    with study.repository._connect() as conn:
        assignments = [
            dict(row) for row in conn.execute(
                "SELECT * FROM assignments WHERE owner_username != '' ORDER BY due_date"
            ).fetchall()
        ]
    sent_state = load_document("push_reminder_state", {}, "trạng thái nhắc hạn")
    if not isinstance(sent_state, dict):
        sent_state = {}

    results: list[dict[str, Any]] = []
    changed = False
    for task in assignments:
        if bool(task.get("completed")):
            continue
        due_at = _parse_assignment_due_at(task.get("due_date"))
        if due_at is None:
            continue
        remaining = due_at - current_time
        if remaining <= timedelta(0):
            continue

        username = str(task.get("owner_username", "")).strip()
        if not username:
            continue
        task_id = str(task.get("id", ""))
        for offset, title in REMINDER_MILESTONES:
            lower_bound = max(offset - timedelta(minutes=5), timedelta(0))
            if not lower_bound < remaining <= offset:
                continue
            reminder_key = f"{username}|{task_id}|{due_at.isoformat()}|{int(offset.total_seconds())}"
            if sent_state.get(reminder_key):
                break
            token_results = send_web_push_to_user(
                username,
                title,
                f"{task.get('title', 'Nhiệm vụ')} · {task.get('subject', '')} · hạn {due_at:%d/%m/%Y %H:%M}.",
                "/student#assignments",
            )
            was_sent = any(item.get("status") == "sent" for item in token_results)
            results.append({
                "username": username,
                "task_id": task_id,
                "milestone_seconds": int(offset.total_seconds()),
                "sent": was_sent,
                "devices": len(token_results),
            })
            if was_sent:
                sent_state[reminder_key] = current_time.isoformat(timespec="seconds")
                changed = True
            break

    if changed:
        save_document("push_reminder_state", sent_state)
    return results


def send_push_notification(token: str, title: str, body: str) -> dict[str, Any]:
    if not token.strip():
        return {"status": "skipped", "reason": "missing_token"}
    return send_fcm_message(token, title, body)


def send_notifications_to_registered_devices() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    usernames = get_web_push_usernames()
    for username in usernames:
        for payload in _build_notification_payloads_for_user(username):
            for token in get_user_web_tokens(username):
                result = send_fcm_message(token, payload["title"], payload["body"])
                results.append({
                    "username": username,
                    "token": token,
                    "device_type": "web",
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

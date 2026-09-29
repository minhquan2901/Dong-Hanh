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
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
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
PUSH_SCHEDULE_STATE_FILE = data_file("push_schedule_state.json")
MOBILE_TOKEN_FILE = data_file("mobile_tokens.json")
MOBILE_PUSH_SUBSCRIPTIONS_FILE = data_file("mobile_push_subscriptions.json")
EMAIL_PREFERENCES_FILE = data_file("email_preferences.json")
REMINDER_PREFERENCES_FILE = data_file("reminder_preferences.json")
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
SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "15"))
STUDY_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

# (mốc thời gian còn lại, tiêu đề, bề rộng cửa sổ chấp nhận)
# Cửa sổ phải nhỏ hơn khoảng cách giữa hai mốc liên tiếp, nếu không sẽ có
# lúc 1 nhiệm vụ khớp đồng thời vào cả hai mốc và gửi 2 thông báo.
REMINDER_MILESTONES = (
    (timedelta(days=1), "Nhiệm vụ còn 1 ngày", timedelta(minutes=30)),
    (timedelta(hours=1), "Nhiệm vụ còn 1 giờ", timedelta(minutes=15)),
    (timedelta(minutes=10), "Nhiệm vụ còn 10 phút", timedelta(minutes=4)),
    (timedelta(minutes=5), "Nhiệm vụ còn 5 phút", timedelta(minutes=4)),
)
# Chỉ cần xét các nhiệm vụ chưa xong và còn hạn trong tầm mốc xa nhất (1 ngày).
REMINDER_HORIZON = timedelta(days=1)
REMINDER_MILESTONE_SECONDS = tuple(int(offset.total_seconds()) for offset, _, _ in REMINDER_MILESTONES)

# Các lỗi FCM báo token đã chết. Gặp lỗi này thì xoá token khỏi mọi nguồn dữ liệu
# thay vì giữ lại làm mỗi lần gửi sau đều thất bại.
FCM_ERROR_UNREGISTERED = (
    "registration-token-not-registered",
    "registration-token-not-registered-mismatch",
    "Requested entity was not found.",
)

DEFAULT_REMINDER_PREFERENCES = {
    "deadline": True,
    "schedule": True,
}

# Nhịch 1 phút: cửa sổ hẹp nhất là 4 phút nên cron 5 phút sẽ dễ trượt mốc.
REMINDER_TICK_SECONDS = int(os.getenv("REMINDER_TICK_SECONDS", "60"))
REMINDER_TICK_ENABLED = os.getenv("REMINDER_TICK_ENABLED", "true").strip().lower() == "true"

PUSH_STATUS_FILE = data_file("push_status.json")
STATUS_HISTORY_LIMIT = 5


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

    subscriptions = load_document("web_push_subscriptions", {})
    if not isinstance(subscriptions, dict):
        subscriptions = {}
    tokens = subscriptions.get(clean_username, [])
    if not isinstance(tokens, list):
        tokens = []
    if clean_token not in tokens:
        tokens.append(clean_token)
    subscriptions[clean_username] = tokens
    save_document("web_push_subscriptions", subscriptions)
    return len(tokens)


def get_user_web_tokens(username: str) -> list[str]:
    subscriptions = load_document("web_push_subscriptions", {})
    if not isinstance(subscriptions, dict):
        return []
    tokens = subscriptions.get(str(username or "").strip(), [])
    return [str(token) for token in tokens if str(token).strip()] if isinstance(tokens, list) else []


def remove_user_web_tokens(username: str) -> None:
    target = str(username or "").strip()
    if not target:
        return
    subscriptions = load_document("web_push_subscriptions", {})
    if not isinstance(subscriptions, dict) or target not in subscriptions:
        return
    subscriptions.pop(target, None)
    save_document("web_push_subscriptions", subscriptions)


def rename_user_web_tokens(old_username: str, new_username: str) -> None:
    old_name = str(old_username or "").strip()
    new_name = str(new_username or "").strip()
    if not old_name or not new_name or old_name == new_name:
        return
    subscriptions = load_document("web_push_subscriptions", {})
    if not isinstance(subscriptions, dict):
        raise RuntimeError("Dữ liệu token thông báo không hợp lệ.")
    old_tokens = subscriptions.pop(old_name, [])
    if not isinstance(old_tokens, list):
        raise RuntimeError("Danh sách token thông báo không hợp lệ.")
    new_tokens = subscriptions.get(new_name, [])
    if not isinstance(new_tokens, list):
        raise RuntimeError("Danh sách token thông báo không hợp lệ.")
    subscriptions[new_name] = list(dict.fromkeys([*new_tokens, *old_tokens]))
    save_document("web_push_subscriptions", subscriptions)


def get_web_push_usernames() -> list[str]:
    subscriptions = load_document("web_push_subscriptions", {})
    if not isinstance(subscriptions, dict):
        return []
    return [str(username) for username, tokens in subscriptions.items() if isinstance(tokens, list) and tokens]


# ---- Token dien thoai theo tung tai khoan ----
# WEB_PUSH_SUBSCRIPTIONS_FILE giu token web. Token dien thoai (FCM app / APNs)
# phai luu rieng theo username, neu khong thi moi thong bao se gui ve toan bo
# may cua tat ca nguoi dung.
def register_user_mobile_token(username: str, token: str) -> int:
    clean_username = str(username or "").strip()
    clean_token = str(token or "").strip()
    if not clean_username or not clean_token:
        raise ValueError("Tên tài khoản và token điện thoại không được để trống.")

    subscriptions = load_document("mobile_push_subscriptions", {})
    if not isinstance(subscriptions, dict):
        subscriptions = {}
    tokens = subscriptions.get(clean_username, [])
    if not isinstance(tokens, list):
        tokens = []
    if clean_token not in tokens:
        tokens.append(clean_token)
    subscriptions[clean_username] = tokens
    save_document("mobile_push_subscriptions", subscriptions)
    return len(tokens)


def get_user_mobile_tokens(username: str) -> list[str]:
    subscriptions = load_document("mobile_push_subscriptions", {})
    if not isinstance(subscriptions, dict):
        return []
    tokens = subscriptions.get(str(username or "").strip(), [])
    return [str(token) for token in tokens if str(token).strip()] if isinstance(tokens, list) else []


def remove_user_mobile_tokens(username: str) -> None:
    target = str(username or "").strip()
    if not target:
        return
    subscriptions = load_document("mobile_push_subscriptions", {})
    if not isinstance(subscriptions, dict) or target not in subscriptions:
        return
    subscriptions.pop(target, None)
    save_document("mobile_push_subscriptions", subscriptions)


def rename_user_mobile_tokens(old_username: str, new_username: str) -> None:
    old_name = str(old_username or "").strip()
    new_name = str(new_username or "").strip()
    if not old_name or not new_name or old_name == new_name:
        return
    subscriptions = load_document("mobile_push_subscriptions", {})
    if not isinstance(subscriptions, dict):
        return
    old_tokens = subscriptions.pop(old_name, [])
    if not isinstance(old_tokens, list):
        return
    new_tokens = subscriptions.get(new_name, [])
    if not isinstance(new_tokens, list):
        new_tokens = []
    subscriptions[new_name] = list(dict.fromkeys([*new_tokens, *old_tokens]))
    save_document("mobile_push_subscriptions", subscriptions)


def get_mobile_push_usernames() -> list[str]:
    subscriptions = load_document("mobile_push_subscriptions", {})
    if not isinstance(subscriptions, dict):
        return []
    return [str(username) for username, tokens in subscriptions.items() if isinstance(tokens, list) and tokens]


def remove_token_everywhere(token: str) -> None:
    """Xoa token da hong (ung app, doi may) khoi ca du lieu web lan dien thoai.

    Token FCM hong se lam moi lan gui that bai; giu lai chi lam cham he thong.
    """
    clean_token = str(token or "").strip()
    if not clean_token:
        return

    for path in (WEB_PUSH_SUBSCRIPTIONS_FILE, MOBILE_PUSH_SUBSCRIPTIONS_FILE):
        key = "mobile_push_subscriptions" if path == MOBILE_PUSH_SUBSCRIPTIONS_FILE else "web_push_subscriptions"
        subscriptions = load_document(key, {})
        if not isinstance(subscriptions, dict) or not any(
            isinstance(tokens, list) and clean_token in tokens for tokens in subscriptions.values()
        ):
            continue
        for username in list(subscriptions):
            tokens = subscriptions.get(username)
            if isinstance(tokens, list):
                subscriptions[username] = [item for item in tokens if item != clean_token]
        save_document(key, subscriptions)

    for path in (WEB_TOKEN_FILE, MOBILE_TOKEN_FILE, DEVICE_TOKEN_FILE):
        tokens = _read_tokens(path) if path.exists() else []
        if clean_token in tokens:
            _write_tokens(path, [item for item in tokens if item != clean_token])


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


# ---- Tùy chọn nhắc theo từng loại ----
def get_reminder_preferences(username: str) -> dict[str, bool]:
    target = str(username or "").strip()
    if not target:
        return dict(DEFAULT_REMINDER_PREFERENCES)
    all_prefs = load_document("reminder_preferences", {})
    stored = all_prefs.get(target, {}) if isinstance(all_prefs, dict) else {}
    stored = stored if isinstance(stored, dict) else {}
    return {
        key: bool(stored.get(key, default))
        for key, default in DEFAULT_REMINDER_PREFERENCES.items()
    }


def set_reminder_preferences(username: str, updates: dict[str, Any]) -> dict[str, bool]:
    target = str(username or "").strip()
    if not target:
        raise ValueError("Tên tài khoản không được để trống.")
    all_prefs = load_document("reminder_preferences", {})
    if not isinstance(all_prefs, dict):
        all_prefs = {}
    stored = all_prefs.get(target, {})
    stored = stored if isinstance(stored, dict) else {}
    for key in DEFAULT_REMINDER_PREFERENCES:
        if key in updates:
            stored[key] = bool(updates[key])
    all_prefs[target] = stored
    save_document("reminder_preferences", all_prefs)
    return get_reminder_preferences(target)


# ---- Trạng thái để người dùng tự kiểm tra khi thông báo im ----
def get_push_status(username: str) -> dict[str, Any]:
    target = str(username or "").strip()
    all_status = load_document("push_status", {})
    if not isinstance(all_status, dict) or target not in all_status:
        web_devices = len(get_user_web_tokens(target))
        mobile_devices = len(get_user_mobile_tokens(target))
        return {
            "web_devices": web_devices,
            "mobile_devices": mobile_devices,
            "registered_at": None,
            "last_success_at": None,
            "last_error": None,
            "last_reminder_at": None,
            "reminders": get_reminder_preferences(target),
            "expected": bool(web_devices or mobile_devices),
        }
    entry = all_status.get(target)
    entry = entry if isinstance(entry, dict) else {}
    reminders = get_reminder_preferences(target)
    return {
        "web_devices": len(get_user_web_tokens(target)),
        "mobile_devices": len(get_user_mobile_tokens(target)),
        "registered_at": entry.get("registered_at"),
        "last_success_at": entry.get("last_success_at"),
        "last_error": entry.get("last_error"),
        "last_reminder_at": entry.get("last_reminder_at"),
        "reminders": reminders,
        "expected": bool(get_user_web_tokens(target) or get_user_mobile_tokens(target)),
    }


def _update_push_status(username: str, **fields: Any) -> None:
    target = str(username or "").strip()
    if not target:
        return
    all_status = load_document("push_status", {})
    if not isinstance(all_status, dict):
        all_status = {}
    entry = all_status.get(target)
    entry = entry if isinstance(entry, dict) else {}
    history = entry.get("history")
    entry["history"] = history if isinstance(history, list) else []
    for key, value in fields.items():
        entry[key] = value
    entry.setdefault("registered_at", datetime.now(STUDY_TIMEZONE).isoformat(timespec="seconds"))
    all_status[target] = entry
    save_document("push_status", all_status)


def record_push_success(username: str, now: datetime | None = None) -> None:
    current = now or datetime.now(STUDY_TIMEZONE)
    _update_push_status(
        username,
        last_success_at=current.isoformat(timespec="seconds"),
        last_error=None,
    )


def record_push_error(username: str, error: str) -> None:
    _update_push_status(username, last_error=str(error)[:200])


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
    """Gửi email thật qua SMTP.

    Trước đây hàm này gọi `http://host:port/sendmail` — đó không phải giao thức
    SMTP nên không có máy chủ nào nhận được, và mọi lỗi bị nuốt chung thành
    `error` khiến việc gửi hỏng không ai nhận ra.
    """
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

    message = EmailMessage()
    message["From"] = formataddr(("StudySync", SMTP_FROM))
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        smtp_class = smtplib.SMTP_SSL if SMTP_PORT == 465 else smtplib.SMTP
        with smtp_class(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
            smtp.ehlo()
            if SMTP_PORT != 465 and smtp.has_extn("starttls"):
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(message)
        return {"status": "sent", "recipient": recipient, "subject": subject}
    except (smtplib.SMTPException, OSError) as exc:
        # Báo đúng loại lỗi để gọi ra ngoài biết là cấu hình sai hay mạng hỏng.
        return {
            "status": "error",
            "recipient": recipient,
            "subject": subject,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


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


def _minutes_until_lesson(lesson: dict[str, Any], now: datetime | None = None) -> int | None:
    today = (now or datetime.now(STUDY_TIMEZONE)).astimezone(STUDY_TIMEZONE)
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
        lesson_dt = datetime.combine(today.date(), start_time, tzinfo=STUDY_TIMEZONE)
        if lesson_dt <= today:
            return None
    else:
        lesson_dt = datetime.combine((today.date() + timedelta(days=days_ahead)), start_time, tzinfo=STUDY_TIMEZONE)

    return int((lesson_dt - today).total_seconds() // 60)


def _build_notification_payloads_for_user(username: str, now: datetime | None = None) -> list[dict[str, str]]:
    owner_username = str(username or "").strip()
    if not owner_username:
        return []
    study = StudyBus()
    payloads: list[dict[str, str]] = []

    for lesson in study.schedule(owner_username):
        reminder_minutes = int(lesson.get("reminder_minutes", 30))
        minutes_until = _minutes_until_lesson(lesson, now)
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


def _is_web_push_token(token: str) -> bool:
    """WebPush token va token FCM native deu la chuoi nghau cau, phai tra loi tu du lieu da dang ky."""
    clean_token = str(token or "").strip()
    if not clean_token:
        return False
    subscriptions = load_document("web_push_subscriptions", {})
    if isinstance(subscriptions, dict) and any(
        isinstance(tokens, list) and clean_token in tokens for tokens in subscriptions.values()
    ):
        return True
    return False


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

    def _is_unregistered_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return any(marker.lower() in text for marker in FCM_ERROR_UNREGISTERED)

    try:
        is_web_token = _is_web_push_token(token)
        if getattr(messaging, "AndroidConfig", None) is not None and not is_web_token:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        channel_id="studysync_reminders",
                        sound="default",
                        icon="/static/studysync-icon-v2-192.png",
                    ),
                    data={"url": (web_link or f"{PUBLIC_APP_URL}/student").replace(PUBLIC_APP_URL, "")},
                ),
                token=token,
            )
        else:
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
        if _is_unregistered_error(exc):
            # Token đã chết (gỡ app, đổi máy, đổi tài khoản Google). Dọn luôn
            # để không tốn lượt gửi và không báo lỗi mãi cho nhiều thông báo.
            remove_token_everywhere(token)
            return {"status": "unregistered", "title": title, "body": body, "error": str(exc)}
        return {"status": "error", "title": title, "body": body, "error": str(exc)}


def send_push_to_user(
    username: str,
    title: str,
    body: str,
    path: str = "/student",
) -> list[dict[str, Any]]:
    """Gui thong bao den moi thiet bi cua mot tai khoan (ca web lan dien thoai)."""
    link = f"{PUBLIC_APP_URL}/{path.lstrip('/')}"
    results = list(send_web_push_to_user(username, title, body, path))
    results.extend(
        send_fcm_message(token, title, body, web_link=link)
        for token in get_user_mobile_tokens(username)
    )
    if any(item.get("status") == "sent" for item in results):
        record_push_success(username)
    else:
        errors = [str(item.get("error", "")) for item in results if item.get("error")]
        if errors:
            record_push_error(username, errors[0])
    return results


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


def _fetch_pending_assignments(now: datetime) -> list[dict[str, Any]]:
    """Chỉ lấy nhiệm vụ chưa xong và còn hạn trong tầm nhắc gần nhất.

    Trước đây hàm này quét toàn bộ bảng `assignments` mỗi lần chạy, kể cả các
    nhiệm vụ đã hoàn thành hoặc hạn từ nhiều tháng trước.
    """
    # Dat tran SQL du 1 phut vi due_date co the luu giay (:00) va timezone.
    # Loc chinh xac theo datetime trong Python o duoi.
    window_start = (now + REMINDER_HORIZON + timedelta(minutes=1)).isoformat()
    study = StudyBus().repository
    with study._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM assignments "
            "WHERE owner_username != '' AND completed = 0 AND due_date <= :window_start "
            "ORDER BY due_date",
            {"window_start": window_start},
        ).fetchall()
    # due_date lưu dạng TEXT nên so sánh chuỗi chỉ gần đúng; lọc lại bằng datetime thật.
    return [
        task
        for task in study._rows_to_dicts(rows)
        if (due_at := _parse_assignment_due_at(task.get("due_date"))) is not None
        and now < due_at <= now + REMINDER_HORIZON
    ]


def send_due_task_reminders(now: datetime | None = None) -> list[dict[str, Any]]:
    current_time = now or datetime.now(STUDY_TIMEZONE)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=STUDY_TIMEZONE)
    current_time = current_time.astimezone(STUDY_TIMEZONE)
    assignments = _fetch_pending_assignments(current_time)
    sent_state = load_document("push_reminder_state", {}, "trạng thái nhắc hạn")
    if not isinstance(sent_state, dict):
        sent_state = {}

    results: list[dict[str, Any]] = []
    changed = False
    for task in assignments:
        due_at = _parse_assignment_due_at(task.get("due_date"))
        if due_at is None:
            continue
        remaining = due_at - current_time
        if remaining <= timedelta(0):
            continue

        username = str(task.get("owner_username", "")).strip()
        if not username:
            continue
        if not get_reminder_preferences(username).get("deadline", True):
            continue
        task_id = str(task.get("id", ""))
        for offset, title, window in REMINDER_MILESTONES:
            lower_bound = max(offset - window, timedelta(0))
            if not lower_bound < remaining <= offset:
                continue
            reminder_key = f"{username}|{task_id}|{due_at.isoformat()}|{int(offset.total_seconds())}"
            if sent_state.get(reminder_key):
                break
            token_results = send_push_to_user(
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
                _update_push_status(username, last_reminder_at=current_time.isoformat(timespec="seconds"))
                changed = True
            break

    if changed:
        save_document("push_reminder_state", sent_state)
    return results


def run_reminder_tick() -> list[dict[str, Any]]:
    """Một nhịp kiểm tra nhắc hạn. Dùng bởi scheduler nền và endpoint cron."""
    return send_due_task_reminders(datetime.now(STUDY_TIMEZONE))


def send_schedule_reminders(now: datetime | None = None) -> list[dict[str, Any]]:
    """Nhắc lịch học, tôn trọng tùy chọn `schedule` của từng tài khoản."""
    current_time = now or datetime.now(STUDY_TIMEZONE)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=STUDY_TIMEZONE)
    current_time = current_time.astimezone(STUDY_TIMEZONE)

    sent_state = load_document("push_schedule_state", {}, "trạng thái nhắc lịch")
    if not isinstance(sent_state, dict):
        sent_state = {}

    results: list[dict[str, Any]] = []
    changed = False
    for username in list(dict.fromkeys([*get_web_push_usernames(), *get_mobile_push_usernames()])):
        if not get_reminder_preferences(username).get("schedule", True):
            continue
        for payload in _build_notification_payloads_for_user(username, current_time):
            subject = payload.get("title", "")
            if not subject.startswith("Nhắc lịch:"):
                continue
            lesson_info = payload.get("body", "").split(" · còn ")[0]
            reminder_key = f"{username}|{current_time.date()}|{subject}|{lesson_info}"
            if sent_state.get(reminder_key):
                continue
            token_results = send_push_to_user(username, payload["title"], payload["body"], "/student#schedule")
            was_sent = any(item.get("status") == "sent" for item in token_results)
            results.append({
                "username": username,
                "title": payload["title"],
                "sent": was_sent,
                "devices": len(token_results),
            })
            if was_sent:
                sent_state[reminder_key] = current_time.isoformat(timespec="seconds")
                changed = True

    if changed:
        save_document("push_schedule_state", sent_state)
    return results


def send_push_notification(token: str, title: str, body: str) -> dict[str, Any]:
    if not token.strip():
        return {"status": "skipped", "reason": "missing_token"}
    return send_fcm_message(token, title, body)


def send_notifications_to_registered_devices() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    usernames = list(dict.fromkeys([*get_web_push_usernames(), *get_mobile_push_usernames()]))
    for username in usernames:
        for payload in _build_notification_payloads_for_user(username):
            for token in [*get_user_web_tokens(username), *get_user_mobile_tokens(username)]:
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


def send_test_push(token: str, title: str, body: str, device_type: str = "mobile", username: str = "") -> dict[str, Any]:
    if device_type == "web":
        register_web_token(token)
    else:
        register_mobile_token(token)
    if username.strip():
        if device_type == "web":
            register_user_web_token(username, token)
        else:
            register_user_mobile_token(username, token)
    return send_fcm_message(token, title, body)

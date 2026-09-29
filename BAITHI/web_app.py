from __future__ import annotations

import os
import secrets
import threading
import time
import traceback
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from auth_service import (
    authenticate_user,
    create_parent_link_request,
    get_link_requests_for_student,
    get_students_for_parent,
    get_user_by_username,
    load_users,
    register_user,
    respond_to_parent_link_request,
    set_secondary_pin,
    set_pin_login_enabled,
    update_linked_student,
    update_account,
    verify_secondary_pin,
)
from backend.notification_service import (
    FIREBASE_VAPID_KEY,
    REMINDER_TICK_ENABLED,
    REMINDER_TICK_SECONDS,
    firebase_push_ready,
    get_push_status,
    get_reminder_preferences,
    get_user_mobile_tokens,
    get_user_web_tokens,
    list_user_devices,
    register_user_mobile_token,
    register_user_web_token,
    remove_user_device,
    remove_user_mobile_tokens,
    remove_user_web_tokens,
    run_reminder_tick,
    send_completion_notifications,
    send_due_task_reminders,
    send_push_to_user,
    send_schedule_reminders,
    send_web_push_to_user,
    set_reminder_preferences,
)
from bus.study_bus import StudyBus
from backend.schedule_ocr import (
    MAX_TIMETABLE_IMAGE_BYTES,
    TimetableImageError,
    extract_timetable_slots,
    timetable_ocr_available,
)
from owner_auth import (
    authenticate_owner,
    create_owner_token,
    create_user_token,
    owner_configuration_error,
    verify_owner_token,
    verify_user_token,
)
from owner_service import delete_managed_user, get_owner_overview, list_managed_users, managed_user_by_id, record_successful_feature_use, rename_managed_user, set_managed_user_active
from data_storage import account_data_status
from db import is_postgres, load_document, storage_status
from feedback_service import create_report, list_reports, mark_report_read
from username_policy import (
    generate_suggested_username,
    get_username_bot_status,
    resolve_signup_violation,
    resolve_username_violation,
    scan_registered_users,
    set_username_bot_enabled,
    validate_class_name,
    validate_display_name,
    validate_username,
)

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="StudySync Unified App")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))

_REMINDER_THREAD: threading.Thread | None = None
_REMINDER_STOP = threading.Event()


@app.on_event("startup")
def warm_up_database() -> None:
    """Mo ket noi Neon va nap san danh sach tai khoan khi app khoi dong.

    Neon scale-to-zero nen lan ket noi dau tien rat cham (2-5 giay). Nap san
    luc khoi dong giup nguoi dung khong phai doi mot lan dang nhap.
    """
    if is_postgres():
        try:
            load_document("users", {"users": []}, "tai khoan")
        except Exception:  # pragma: no cover - app van khoi dong duoc neu DB loi
            pass


@app.on_event("shutdown")
def stop_reminder_scheduler() -> None:
    _stop_reminder_scheduler()


def _reminder_loop() -> None:
    """Vòng lặp gửi thông báo chạy nền trong tiến trình server.

    Trước đây toàn bộ nhắc hạn phụ thuộc cron ngoài gọi `/api/internal/push-due`.
    Cửa sổ hẹp nhất chỉ 4 phút nên cron chạy mỗi 5 phút sẽ dễ trượt mốc.
    """
    while not _REMINDER_STOP.is_set():
        try:
            run_reminder_tick()
            send_schedule_reminders()
        except Exception:  # pragma: no cover - vòng lặp không được chết vì 1 lần lỗi
            traceback.print_exc()
        # wait thay cho sleep để lệnh tắt được phản hồi ngay.
        _REMINDER_STOP.wait(REMINDER_TICK_SECONDS)


def _start_reminder_scheduler() -> None:
    global _REMINDER_THREAD
    if not REMINDER_TICK_ENABLED or _REMINDER_THREAD is not None:
        return
    _REMINDER_STOP.clear()
    _REMINDER_THREAD = threading.Thread(
        target=_reminder_loop,
        name="studysync-reminder-scheduler",
        daemon=True,
    )
    _REMINDER_THREAD.start()


def _stop_reminder_scheduler() -> None:
    global _REMINDER_STOP
    _REMINDER_STOP.set()
    thread = _REMINDER_THREAD
    if thread is None:
        return
    thread.join(timeout=2)
    _REMINDER_THREAD = None


class AuthPayload(BaseModel):
    username: str
    password: str
    full_name: str | None = None
    role: str = "student"
    class_name: str | None = None
    pin: str | None = None


class IdentityUpdatePayload(BaseModel):
    username: str
    new_username: str
    full_name: str
    class_name: str = ""


class ParentLinkPayload(BaseModel):
    parent_username: str
    student_id: str


class LinkRequestResponsePayload(BaseModel):
    student_username: str
    request_id: str
    accept: bool


class StudentProfilePayload(BaseModel):
    parent_username: str
    student_id: str
    full_name: str
    class_name: str = ""
    avatar: str = ""
    is_active: bool = True


class ScheduleSlotPayload(BaseModel):
    session: str
    day: str
    period: int
    subject: str
    lecturer: str = ""
    username: str | None = None


class ScheduleSlotDeletePayload(BaseModel):
    session: str
    day: str
    period: int
    username: str | None = None


class ScheduleSlotBulkPayload(BaseModel):
    slots: list[ScheduleSlotPayload]


class AssignmentPayload(BaseModel):
    title: str
    subject: str
    description: str = ""
    due_date: date
    due_time: time = time(23, 59)
    priority: str = "Trung bình"
    username: str | None = None


class AssignmentCompletionPayload(BaseModel):
    completed: bool
    username: str | None = None


class WebPushRegistrationPayload(BaseModel):
    username: str
    token: str


class WebPushUnregisterPayload(BaseModel):
    username: str


class MobilePushRegistrationPayload(BaseModel):
    username: str
    token: str


class ReminderPreferencePayload(BaseModel):
    username: str
    deadline: bool | None = None
    schedule: bool | None = None
    completion: bool | None = None
    deadline_milestones: list[int] | None = None
    quiet_hours: dict[str, Any] | None = None

class PushDevicePayload(BaseModel):
    username: str
    device_id: str


class SecondaryPinSetupPayload(BaseModel):
    username: str
    password: str
    pin: str


class PinLoginSettingPayload(BaseModel):
    username: str
    password: str
    enabled: bool
    pin: str = ""


class OwnerLoginPayload(BaseModel):
    username: str
    password: str


class OwnerUserStatusPayload(BaseModel):
    is_active: bool


class UsernameBotSettingsPayload(BaseModel):
    enabled: bool
class ProfileUpdatePayload(BaseModel):
    username: str
    full_name: str
    class_name: str = ""
    avatar: str = ""

class PasswordUpdatePayload(BaseModel):
    username: str
    current_password: str
    new_password: str
class OwnerUserEditPayload(BaseModel):
    full_name: str
    class_name: str | None = None
    avatar: str | None = None


class OwnerUserRenamePayload(BaseModel):
    new_username: str
    full_name: str | None = None
    class_name: str | None = None

class ReportPayload(BaseModel):
    username: str
    category: str
    message: str
class ReportReadPayload(BaseModel):
    read: bool
class OwnerLoginResponse(BaseModel):
    token: str
    username: str
    role: str = "owner"


def _require_owner(authorization: str | None) -> None:
    scheme, _, token = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not verify_owner_token(token.strip()):
        raise HTTPException(status_code=401, detail="Phiên owner không hợp lệ hoặc đã hết hạn.")


def _require_user_session(
    authorization: str | None,
    username: str,
    allowed_roles: set[str] | None = None,
):
    scheme, _, token = str(authorization or "").partition(" ")
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=403, detail="Tài khoản không tồn tại.")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa hoặc không còn hoạt động.")
    if scheme.lower() != "bearer" or not verify_user_token(
        token.strip(), username, str(user.get("role", "student")), int(user.get("session_version", 0))
    ):
        raise HTTPException(status_code=401, detail="Vui lòng đăng nhập lại để tiếp tục.")
    if allowed_roles and user.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Không có quyền thực hiện thao tác này.")
    return user


def _record_feature_success(username: str | None, token: str | None, feature: str) -> None:
    clean_username = str(username or "").strip()
    if not clean_username:
        return
    user = get_user_by_username(clean_username)
    if (
        user
        and user.get("is_active", True)
        and user.get("role") in {"student", "parent"}
        and verify_user_token(str(token or ""), clean_username, str(user.get("role")), int(user.get("session_version", 0)))
    ):
        record_successful_feature_use(clean_username, feature)


def _build_student_alerts(student_name: str, score: int, tasks: list[dict]) -> list[dict]:
    alerts: list[dict] = []
    pending = [item for item in tasks if not item.get("completed")]
    today = date.today()
    overdue = []
    due_soon = []
    for item in pending:
        try:
            due_date = datetime.fromisoformat(str(item.get("due_date"))).date()
        except (TypeError, ValueError):
            continue
        if due_date < today:
            overdue.append(item)
        elif due_date == today + timedelta(days=1):
            due_soon.append(item)
        elif due_date <= today + timedelta(days=2):
            due_soon.append(item)

    if overdue:
        alerts.append({
            "level": "danger",
            "title": "Nhiệm vụ đã quá hạn",
            "message": f"{student_name} có {len(overdue)} nhiệm vụ quá hạn. Hãy ưu tiên xử lý ngay hôm nay.",
        })
    elif due_soon:
        due_tomorrow = [
            item for item in due_soon
            if str(item.get("due_date", ""))[:10] == (today + timedelta(days=1)).isoformat()
        ]
        alerts.append({
            "level": "warning",
            "title": "Nhiệm vụ còn 1 ngày",
            "message": (
                f"{len(due_tomorrow)} nhiệm vụ đến hạn ngày mai: {due_tomorrow[0].get('title', 'Nhiệm vụ')}."
                if due_tomorrow
                else f"{len(due_soon)} nhiệm vụ sắp đến hạn: {due_soon[0].get('title', 'Nhiệm vụ')}."
            ),
        })

    if not pending:
        alerts.append({
            "level": "info",
            "title": "Hoàn tất tốt",
            "message": f"{student_name} đã hoàn thành tất cả nhiệm vụ trong danh sách hiện tại.",
        })
        return alerts

    if score < 50 or len(pending) >= 3:
        alerts.append({
            "level": "danger",
            "title": "Tiến độ đang giảm",
            "message": f"{student_name} còn {len(pending)} nhiệm vụ chưa hoàn thành. Nên chia nhỏ kế hoạch học hôm nay.",
        })
    elif score < 80:
        alerts.append({
            "level": "warning",
            "title": "Cần nhắc nhở",
            "message": f"{student_name} còn {len(pending)} nhiệm vụ chưa hoàn thành. Hãy duy trì lịch học đều đặn.",
        })
    else:
        alerts.append({
            "level": "success",
            "title": "Tiến độ ổn định",
            "message": f"{student_name} đang duy trì tốt tiến độ và sắp hoàn thành kế hoạch học tập.",
        })

    next_task = min(pending, key=lambda item: str(item.get("due_date", "9999-12-31"))) if pending else None
    if next_task:
        alerts.append({
            "level": "info",
            "title": "Nhiệm vụ sắp hạn",
            "message": f"Cần tập trung vào '{next_task.get('title', 'Nhiệm vụ')}' với hạn {next_task.get('due_date', 'chưa xác định')}.",
        })
    return alerts


def _notifications_for_user(username: str) -> list[dict]:
    user = get_user_by_username(username)
    if not user:
        return []
    study = StudyBus()
    if user.get("role") == "parent":
        students = get_students_for_parent(username)
        if not students:
            return []
        alerts: list[dict] = []
        for student in students:
            student_username = str(student.get("username", ""))
            tasks = study.assignments(student_username)
            stats = study.stats(student_username)
            alerts.extend({
                "student": student.get("full_name") or student.get("username"),
                **alert,
            } for alert in _build_student_alerts(
                student.get("full_name") or student.get("username"),
                int(stats["completion_rate"]),
                tasks,
            ))
        return alerts[:10]
    tasks = study.assignments(username)
    stats = study.stats(username)
    return _build_student_alerts(
        user.get("full_name") or username,
        int(stats["completion_rate"]),
        tasks,
    )


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/login")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "StudySync Unified App"}


@app.get("/manifest.json")
def manifest() -> FileResponse:
    """Manifest cho PWA: de dien thoai co the cai app va nhan thong bao."""
    return FileResponse(ROOT / "manifest.json", media_type="application/manifest+json")


@app.get("/health/data")
def health_data() -> dict[str, object]:
    """Xem du lieu tai khoan con nguyen khong sau moi lan deploy."""
    status = account_data_status()
    return {
        "status": "ok",
        "backend": storage_status()["backend"],
        "data_dir": status["data_dir"],
        "persistent_dir": status["using_persistent_dir"],
        "user_count": status["user_count"],
        "has_session_secret": status["has_session_secret"],
        "files": status["files"],
    }


@app.get("/firebase-messaging-sw.js")
def firebase_messaging_service_worker() -> FileResponse:
    return FileResponse(ROOT / "firebase-messaging-sw.js", media_type="application/javascript")


@app.get("/firebase-notifications.js")
def firebase_notifications_module() -> FileResponse:
    return FileResponse(ROOT / "firebase-notifications.js", media_type="application/javascript")


@app.get("/api/push/config")
def web_push_config() -> dict[str, bool | str]:
    return {
        "vapid_key": FIREBASE_VAPID_KEY,
        "ready": firebase_push_ready(),
        # Da ho tro ca dien thoai qua PWA; truong hop nay giu de tuong thich.
        "desktop_only": False,
    }


@app.post("/api/push/register")
def register_web_push(payload: WebPushRegistrationPayload, authorization: str | None = Header(default=None)):
    _require_user_session(authorization, payload.username, {"student", "parent"})
    user = get_user_by_username(payload.username)
    if not user or user.get("role") not in {"student", "parent"}:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    if not payload.token.strip():
        raise HTTPException(status_code=400, detail="Token thông báo không hợp lệ.")
    try:
        count = register_user_web_token(payload.username, payload.token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Đã bật thông báo trên thiết bị này.",
        "registered_devices": count,
        "registered_desktop_devices": count,
    }


@app.post("/api/push/unregister")
def unregister_web_push(payload: WebPushUnregisterPayload, authorization: str | None = Header(default=None)):
    _require_user_session(authorization, payload.username, {"student", "parent"})
    remove_user_web_tokens(payload.username)
    remove_user_mobile_tokens(payload.username)
    return {"message": "Đã tắt thông báo trên tất cả thiết bị.", "username": payload.username}


@app.post("/api/push/register-mobile")
def register_mobile_push(payload: MobilePushRegistrationPayload, authorization: str | None = Header(default=None)):
    """App điện thoại (Android/iOS) đăng ký FCM token theo đúng tài khoản."""
    _require_user_session(authorization, payload.username, {"student", "parent"})
    user = get_user_by_username(payload.username)
    if not user or user.get("role") not in {"student", "parent"}:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    if not payload.token.strip():
        raise HTTPException(status_code=400, detail="Token thông báo không hợp lệ.")
    try:
        count = register_user_mobile_token(payload.username, payload.token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Đã bật thông báo trên điện thoại.", "registered_devices": count}


@app.get("/api/push/status")
def push_status(
    username: str = Query(...),
    authorization: str | None = Header(default=None),
):
    _require_user_session(authorization, username)
    status = get_push_status(username)
    status["devices"] = list_user_devices(username)
    return status


@app.get("/api/push/devices")
def list_push_devices(
    username: str = Query(...),
    authorization: str | None = Header(default=None),
):
    _require_user_session(authorization, username)
    return {"devices": list_user_devices(username)}


@app.post("/api/push/devices/remove")
def remove_push_device(payload: PushDevicePayload, authorization: str | None = Header(default=None)):
    _require_user_session(authorization, payload.username, {"student", "parent"})
    if not remove_user_device(payload.username, payload.device_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy thiết bị này.")
    return {"message": "Đã tắt thông báo trên thiết bị.", "username": payload.username}


@app.post("/api/push/test")
def send_test_push_to_account(payload: PushDevicePayload, authorization: str | None = Header(default=None)):
    _require_user_session(authorization, payload.username, {"student", "parent"})
    results = send_push_to_user(
        payload.username,
        "StudySync: thông báo thử",
        "Thông báo thử đã tới thiết bị này. Nếu bạn thấy nó, cấu hình thông báo đang chạy tốt.",
        "/student" if get_user_by_username(payload.username).get("role") == "student" else "/parent",
    )
    sent = any(item.get("status") == "sent" for item in results)
    return {
        "message": "Đã gửi thông báo thử." if sent else "Không có thiết bị nào nhận được thông báo thử.",
        "sent": sent,
        "devices": len(results),
        "results": results,
    }


@app.post("/api/push/preferences")
def update_push_preferences(payload: ReminderPreferencePayload, authorization: str | None = Header(default=None)):
    _require_user_session(authorization, payload.username, {"student", "parent"})
    user = get_user_by_username(payload.username)
    if not user or user.get("role") not in {"student", "parent"}:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    updates = {
        key: value
        for key, value in (
            ("deadline", payload.deadline),
            ("schedule", payload.schedule),
            ("completion", payload.completion),
            ("deadline_milestones", payload.deadline_milestones),
            ("quiet_hours", payload.quiet_hours),
        )
        if value is not None
    }
    if not updates:
        raise HTTPException(status_code=400, detail="Chưa chọn loại nhắc nào để thay đổi.")
    return {"reminders": set_reminder_preferences(payload.username, updates)}


@app.get("/api/push/preferences")
def read_push_preferences(
    username: str = Query(...),
    authorization: str | None = Header(default=None),
):
    _require_user_session(authorization, username)
    return {"reminders": get_reminder_preferences(username), "devices": list_user_devices(username)}


@app.post("/api/internal/push-due")
def trigger_due_task_pushes(x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret")):
    expected_secret = os.getenv("PUSH_CRON_SECRET", "")
    if not expected_secret:
        raise HTTPException(status_code=503, detail="Chưa cấu hình PUSH_CRON_SECRET.")
    if not x_cron_secret or not secrets.compare_digest(x_cron_secret, expected_secret):
        raise HTTPException(status_code=403, detail="Không được phép gọi tác vụ này.")
    return _locked_reminder_tick()


def _locked_reminder_tick() -> dict[str, Any]:
    """Cron và worker cùng gọi một hàm, nên khoá chống gửi trùng ở một chỗ.

    Import cục bộ để tránh vòng lặp import giữa web_app và reminder_worker.
    """
    from reminder_worker import reminder_lock

    with reminder_lock() as acquired:
        if not acquired:
            return {"skipped": "locked", "reminders": [], "schedule": []}
        return {"reminders": send_due_task_reminders(), "schedule": send_schedule_reminders()}


@app.get("/api/push/health")
def push_health(
    username: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Tóm tắt khả năng gửi để người dùng tự kiểm tra khi thông báo im."""
    _require_user_session(authorization, username)
    status = get_push_status(username)
    return {
        "ready": firebase_push_ready(),
        "expected": status["expected"],
        "devices": len(status.get("devices", [])),
        "last_success_at": status["last_success_at"],
        "last_error": status["last_error"],
        "consecutive_errors": status["consecutive_errors"],
    }


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


@app.get("/student")
async def student_dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="student_dashboard.html")


@app.get("/parent")
async def parent_dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="parent_dashboard.html")


@app.get("/owner")
async def owner_dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="owner.html")

@app.get("/account")
async def account_page(request: Request):
    return templates.TemplateResponse(request=request, name="account.html")


@app.post("/api/owner/login", response_model=OwnerLoginResponse)
def owner_login(payload: OwnerLoginPayload):
    config_error = owner_configuration_error()
    if config_error:
        raise HTTPException(status_code=503, detail=config_error)
    if not authenticate_owner(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="Thông tin đăng nhập owner không đúng.")
    try:
        token = create_owner_token(payload.username.strip())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"token": token, "username": payload.username.strip(), "role": "owner"}


@app.get("/api/owner/overview")
def owner_overview(authorization: str | None = Header(default=None)):
    _require_owner(authorization)
    try:
        return get_owner_overview()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Không đọc được dữ liệu thống kê owner.") from exc


@app.get("/api/owner/users")
def owner_users(authorization: str | None = Header(default=None)):
    _require_owner(authorization)
    try:
        return {"users": list_managed_users()}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Không đọc được danh sách người dùng.") from exc


@app.patch("/api/owner/users/{user_id}/status")
def owner_set_user_status(
    user_id: str,
    payload: OwnerUserStatusPayload,
    authorization: str | None = Header(default=None),
):
    _require_owner(authorization)
    if not set_managed_user_active(user_id, payload.is_active):
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    return {"message": "Đã cập nhật trạng thái tài khoản."}


@app.delete("/api/owner/users/{user_id}")
def owner_delete_user(user_id: str, authorization: str | None = Header(default=None)):
    _require_owner(authorization)
    if not delete_managed_user(user_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    return {"message": "Đã xóa tài khoản và dữ liệu liên quan."}


@app.get("/api/owner/username-bot")
def owner_username_bot_status(authorization: str | None = Header(default=None)):
    _require_owner(authorization)
    return get_username_bot_status()


@app.patch("/api/owner/username-bot")
def owner_update_username_bot(
    payload: UsernameBotSettingsPayload,
    authorization: str | None = Header(default=None),
):
    _require_owner(authorization)
    return set_username_bot_enabled(payload.enabled)


@app.post("/api/owner/username-bot/scan")
def owner_scan_usernames(authorization: str | None = Header(default=None)):
    _require_owner(authorization)
    return scan_registered_users(load_users())


@app.post("/api/owner/username-bot/violations/{username}/review")
def owner_review_username_violation(
    username: str,
    authorization: str | None = Header(default=None),
):
    _require_owner(authorization)
    if not resolve_username_violation(username):
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo đang chờ.")
    return get_username_bot_status()


@app.post("/api/internal/username-bot-scan")
def trigger_username_bot_scan(x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret")):
    expected_secret = os.getenv("USERNAME_BOT_CRON_SECRET", "")
    if not expected_secret:
        raise HTTPException(status_code=503, detail="Chưa cấu hình USERNAME_BOT_CRON_SECRET.")
    if not x_cron_secret or not secrets.compare_digest(x_cron_secret, expected_secret):
        raise HTTPException(status_code=403, detail="Không được phép gọi tác vụ này.")
    return scan_registered_users(load_users())


@app.post("/api/auth/login")
def login(payload: AuthPayload):
    user = authenticate_user(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng.")
    if user.get("pin_login_enabled", False):
        if not payload.pin:
            return {"requires_pin": True, "message": "Nhập mã PIN để tiếp tục đăng nhập."}
        if not verify_secondary_pin(payload.username, payload.pin):
            raise HTTPException(status_code=401, detail="Mã PIN không đúng.")
    try:
        session_token = create_user_token(str(user.get("username", "")), str(user.get("role", "student")), int(user.get("session_version", 0)))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Chưa cấu hình khóa phiên đăng nhập an toàn.") from exc

    sanitized = {
        "id": user.get("id"),
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "role": user.get("role", "student"),
        "class_name": user.get("class_name", ""),
        "student_id": user.get("student_id", ""),
        "avatar": user.get("avatar", ""),
        "parent_username": user.get("parent_username", ""),
        "is_active": user.get("is_active", True),
        "pin_login_enabled": bool(user.get("pin_login_enabled", False)),
    }
    return {
        "message": "Đăng nhập thành công.",
        "user": sanitized,
        "token": session_token,
        "identity_update_required": False,
        "identity_reasons": [],
    }


@app.post("/api/auth/register")
def register(payload: AuthPayload):
    if payload.role.strip().lower() not in {"student", "parent"}:
        raise HTTPException(status_code=400, detail="Chỉ được đăng ký tài khoản học sinh hoặc phụ huynh.")
    if payload.role.strip().lower() == "student" and not (payload.full_name or "").strip():
        raise HTTPException(status_code=400, detail="Họ tên không được để trống.")

    policy_enabled = get_username_bot_status()["enabled"]
    class_name = payload.class_name or ""
    if policy_enabled:
        if payload.role.strip().lower() == "student":
            class_valid, class_result = validate_class_name(class_name)
            if class_valid:
                class_name = class_result

    try:
        user = register_user(
            username=payload.username,
            password=payload.password,
            role=payload.role,
            full_name=payload.full_name or payload.username,
            class_name=class_name,
        )
    except ValueError as exc:
        headers = None
        if "đã tồn tại" in str(exc).casefold():
            headers = {"X-Username-Suggestions": ",".join(generate_suggested_username(
                payload.full_name or payload.username,
                existing_usernames=[str(item.get("username", "")) for item in load_users()],
            ))}
        raise HTTPException(status_code=400, detail=str(exc), headers=headers) from exc

    safe_user = {
        "id": user.get("id"),
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "role": user.get("role", "student"),
        "class_name": user.get("class_name", ""),
        "student_id": user.get("student_id", ""),
        "avatar": user.get("avatar", ""),
        "parent_username": user.get("parent_username", ""),
        "is_active": user.get("is_active", True),
        "pin_login_enabled": bool(user.get("pin_login_enabled", False)),
    }
    resolve_signup_violation(str(user.get("username", "")))
    if policy_enabled:
        scan_registered_users(load_users())
    return {"message": "Tạo tài khoản thành công.", "user": safe_user}


@app.post("/api/profile/identity")
def update_required_identity(
    payload: IdentityUpdatePayload,
    authorization: str | None = Header(default=None),
):
    current_user = _require_user_session(authorization, payload.username)
    username_valid, username_message = validate_username(payload.new_username)
    if not username_valid:
        raise HTTPException(
            status_code=400,
            detail=username_message,
            headers={"X-Username-Suggestions": ",".join(generate_suggested_username(
                payload.full_name,
                existing_usernames=[str(item.get("username", "")) for item in load_users()],
            ))},
        )
    name_valid, name_message = validate_display_name(payload.full_name)
    if not name_valid:
        raise HTTPException(status_code=400, detail=name_message)
    class_name = payload.class_name
    if current_user.get("role") == "student":
        class_valid, class_result = validate_class_name(payload.class_name)
        if not class_valid:
            raise HTTPException(status_code=400, detail=class_result)
        class_name = class_result
    try:
        updated = rename_managed_user(
            payload.username, payload.new_username, payload.full_name, class_name
        )
        new_token = create_user_token(
            str(updated["username"]),
            str(updated.get("role", "student")),
            int(updated.get("session_version", 0)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Đã cập nhật username và hồ sơ. Hãy đăng nhập lại bằng username mới.",
        "user": {
            "id": updated.get("id"),
            "username": updated.get("username"),
            "full_name": updated.get("full_name"),
            "role": updated.get("role"),
            "class_name": updated.get("class_name", ""),
            "student_id": updated.get("student_id", ""),
            "avatar": updated.get("avatar", ""),
            "parent_username": updated.get("parent_username", ""),
            "is_active": updated.get("is_active", True),
            "pin_login_enabled": bool(updated.get("pin_login_enabled", False)),
        },
        "token": new_token,
    }


@app.get("/api/dashboard/student")
def student_dashboard(username: str = Query(...), authorization: str | None = Header(default=None)):
    user = _require_user_session(authorization, username, {"student"})
    if not user or user.get("role") != "student" or not user.get("is_active", True):
        raise HTTPException(status_code=404, detail="Không tìm thấy học sinh.")

    study = StudyBus()
    tasks = study.assignments(username)
    total = len(tasks)
    completed = sum(1 for item in tasks if item.get("completed"))
    pending = total - completed
    completion_rate = round(completed / total * 100) if total else 0
    alerts = _build_student_alerts(user.get("full_name") or user.get("username"), completion_rate, tasks)

    return {
        "student": {
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "class_name": user.get("class_name", ""),
            "student_id": user.get("student_id", ""),
            "avatar": user.get("avatar", ""),
            "is_active": user.get("is_active", True),
        },
        "stats": {
            "total": total,
            "completed": completed,
            "pending": pending,
            "completion_rate": completion_rate,
        },
        "schedule": study.schedule(username),
        "assignments": tasks,
        "alerts": alerts,
    }


@app.get("/api/notifications")
def notifications(username: str = Query(...), authorization: str | None = Header(default=None)):
    user = _require_user_session(authorization, username)
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")
    return {"notifications": _notifications_for_user(username)}


@app.post("/api/security/pin")
def setup_secondary_pin(payload: SecondaryPinSetupPayload, authorization: str | None = Header(default=None)):
    _require_user_session(authorization, payload.username)
    try:
        set_secondary_pin(payload.username, payload.password, payload.pin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Đã đăng ký mã PIN cấp 2."}


@app.post("/api/security/pin-login")
def update_pin_login_setting(payload: PinLoginSettingPayload, authorization: str | None = Header(default=None)):
    _require_user_session(authorization, payload.username)
    try:
        set_pin_login_enabled(payload.username, payload.password, payload.enabled, payload.pin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Đã cập nhật cài đặt PIN đăng nhập.", "enabled": payload.enabled}


@app.get("/api/dashboard/parent")
def parent_dashboard(username: str = Query(...), authorization: str | None = Header(default=None)):
    parent = _require_user_session(authorization, username, {"parent"})
    if not parent or parent.get("role") != "parent" or not parent.get("is_active", True):
        raise HTTPException(status_code=404, detail="Không tìm thấy phụ huynh.")

    students = get_students_for_parent(username)

    study = StudyBus()
    tasks_by_username = {
        str(student.get("username", "")): study.assignments(str(student.get("username", "")))
        for student in students
    }
    tasks = [task for student_tasks in tasks_by_username.values() for task in student_tasks]
    completed_tasks = sum(1 for item in tasks if item.get("completed"))
    total_tasks = len(tasks)
    overall_completion = round(completed_tasks / total_tasks * 100) if total_tasks else 0

    student_rows = []
    for student in students:
        student_tasks = tasks_by_username.get(str(student.get("username", "")), [])
        student_total = len(student_tasks)
        student_completed = sum(1 for task in student_tasks if task.get("completed"))
        row_rate = round(student_completed / student_total * 100) if student_total else 0
        student_rows.append({
            "username": student.get("username"),
            "full_name": student.get("full_name"),
            "class_name": student.get("class_name", ""),
            "student_id": student.get("student_id", ""),
            "avatar": student.get("avatar", ""),
            "is_active": student.get("is_active", True),
            "completion_rate": row_rate,
            "alerts": _build_student_alerts(student.get("full_name") or student.get("username"), row_rate, student_tasks),
            "schedule": study.schedule(str(student.get("username", ""))),
            "completed_tasks": student_completed,
            "pending_tasks": student_total - student_completed,
            "total_tasks": student_total,
        })

    alerts = []
    for student in student_rows:
        alerts.extend([{
            "student": student["full_name"],
            **alert,
        } for alert in student["alerts"]])

    return {
        "overview": {
            "total_students": len(student_rows),
            "completed_tasks": completed_tasks,
            "pending_tasks": max(total_tasks - completed_tasks, 0),
            "completion_rate": overall_completion,
        },
        "students": student_rows,
        "tasks": [
            {
                "title": task.get("title", "Nhiệm vụ"),
                "subject": task.get("subject", "Không xác định"),
                "student_name": next(
                    (row["full_name"] for row in student_rows if row["username"] == task.get("owner_username")),
                    "Học sinh",
                ),
                "completed": bool(task.get("completed")),
                "due_date": task.get("due_date", str(date.today())),
            }
            for task in tasks
        ],
        "alerts": alerts[:6],
        "chart": {
            "labels": [student["full_name"] for student in student_rows],
            "values": [student["completion_rate"] for student in student_rows],
        },
    }


@app.put("/api/schedule/slot")
def update_schedule_slot(
    payload: ScheduleSlotPayload,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    _require_user_session(authorization, payload.username or "", {"student"})
    try:
        item = StudyBus().upsert_schedule_slot(
            payload.session, payload.day, payload.period, payload.subject, payload.lecturer, payload.username or ""
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(_record_feature_success, payload.username, authorization.partition(" ")[2] if authorization else None, "schedule")
    if payload.username:
        background_tasks.add_task(
            send_web_push_to_user,
            payload.username,
            "Đã cập nhật thời khóa biểu",
            f"Đã lưu {item.get('subject', 'tiết học')} vào thứ {payload.day}, tiết {payload.period}.",
            "/student#schedule",
        )
    return {
        "message": "Đã cập nhật thời khóa biểu.",
        "notification": {
            "title": "Đã cập nhật thời khóa biểu",
            "message": f"Đã lưu {item.get('subject', 'tiết học')} vào thứ {payload.day}, tiết {payload.period}.",
        },
        "schedule": item,
    }


@app.post("/api/schedule/import-image")
async def import_schedule_from_image(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    x_username: str | None = Header(default=None, alias="X-Username"),
):
    """Doc anh thoi khoa bieu va tra ve cac tiet de nguoi dung xem truoc.

    Khong ghi thang vao thoi khoa bieu. Nguoi dung phai xem lai roi bam luu,
    vi doc may co the nham o trong.
    """
    username = str(x_username or "").strip()
    _require_user_session(authorization, username, {"student"})
    if not timetable_ocr_available():
        raise HTTPException(
            status_code=503,
            detail="Máy chủ chưa cài thư viện đọc ảnh. Chạy: pip install -r requirements.txt",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Ảnh rỗng. Hãy chọn ảnh thời khóa biểu.")
    # Gioi han kich thuoc de tranh doc anh qua lon lam treo may chu.
    if len(raw) > MAX_TIMETABLE_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Ảnh vượt quá dung lượng cho phép. Hãy chụp gọn vùng thời khóa biểu.",
        )
    try:
        slots, warnings = extract_timetable_slots(raw)
    except TimetableImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "message": f"Đã đọc {len(slots)} tiết học. Kiểm tra lại rồi bấm Lưu vào thời khóa biểu.",
        "warnings": warnings,
        "slots": [{**slot, "username": username} for slot in slots],
    }


@app.get("/api/schedule/import-image/status")
def schedule_image_import_status(authorization: str | None = Header(default=None)):
    """Cho giao dien biet truoc khi nen hien nut tai anh."""
    return {"available": timetable_ocr_available()}


@app.post("/api/schedule/slots")
def bulk_update_schedule_slots(
    payload: ScheduleSlotBulkPayload,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    username = payload.slots[0].username if payload.slots else ""
    _require_user_session(authorization, username or "", {"student"})
    if any(item.username != username for item in payload.slots):
        raise HTTPException(status_code=400, detail="Các tiết trong một lần lưu phải cùng tài khoản.")
    try:
        slots = [
            {
                "session": item.session,
                "day": item.day,
                "period": item.period,
                "subject": item.subject,
                "lecturer": item.lecturer,
                "username": item.username or "",
            }
            for item in payload.slots
        ]
        saved = StudyBus().upsert_schedule_slots(slots)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if saved:
        background_tasks.add_task(
            _record_feature_success,
            payload.slots[0].username if payload.slots else None,
            authorization.partition(" ")[2] if authorization else None,
            "schedule",
        )
    if payload.slots and payload.slots[0].username:
        background_tasks.add_task(
            send_web_push_to_user,
            payload.slots[0].username,
            "Đã cập nhật thời khóa biểu",
            f"Đã lưu {len(saved)} tiết học vào thời khóa biểu.",
            "/student#schedule",
        )
    return {
        "message": f"Đã lưu {len(saved)} tiết học.",
        "schedule": saved,
        "notification": {
            "title": "Đã cập nhật thời khóa biểu",
            "message": f"Đã lưu {len(saved)} tiết học vào thời khóa biểu.",
        },
    }


@app.delete("/api/schedule/slot")
def delete_schedule_slot(
    payload: ScheduleSlotDeletePayload,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    _require_user_session(authorization, payload.username or "", {"student"})
    deleted = StudyBus().delete_schedule_slot(payload.session, payload.day, payload.period, payload.username or "")
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy tiết học.")
    background_tasks.add_task(_record_feature_success, payload.username, authorization.partition(" ")[2] if authorization else None, "schedule")
    if payload.username:
        background_tasks.add_task(
            send_web_push_to_user,
            payload.username,
            "Đã cập nhật thời khóa biểu",
            "Một tiết học đã được xóa khỏi thời khóa biểu.",
            "/student#schedule",
        )
    return {"message": "Đã xóa tiết học."}


@app.post("/api/assignments")
def create_assignment(
    payload: AssignmentPayload,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    _require_user_session(authorization, payload.username or "", {"student"})
    try:
        item = StudyBus().add_assignment(
            payload.title, payload.subject, payload.due_date, payload.priority,
            payload.username or "", payload.due_time, payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(_record_feature_success, payload.username, authorization.partition(" ")[2] if authorization else None, "assignments")
    if payload.username:
        background_tasks.add_task(
            send_web_push_to_user,
            payload.username,
            "Có nhiệm vụ mới",
            f"{item['title']} · hạn {item['due_date']}.",
            "/student#assignments",
        )
    return {"message": "Đã thêm nhiệm vụ.", "assignment": item}


@app.get("/api/assignments/{assignment_id}/events")
def assignment_events(
    assignment_id: str,
    username: str = Query(...),
    authorization: str | None = Header(default=None),
):
    _require_user_session(authorization, username, {"student"})
    study = StudyBus()
    if not any(item.get("id") == assignment_id for item in study.assignments(username)):
        raise HTTPException(status_code=404, detail="Không tìm thấy nhiệm vụ.")
    return {"events": study.assignment_events(assignment_id, username)}


@app.patch("/api/assignments/{assignment_id}")
def update_assignment(
    assignment_id: str,
    payload: AssignmentCompletionPayload,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    _require_user_session(authorization, payload.username or "", {"student"})
    study = StudyBus()
    if not study.set_completed(assignment_id, payload.completed, payload.username or ""):
        raise HTTPException(status_code=404, detail="Không tìm thấy nhiệm vụ.")
    background_tasks.add_task(_record_feature_success, payload.username, authorization.partition(" ")[2] if authorization else None, "assignments")
    if payload.username and payload.completed:
        task = next((item for item in study.assignments(payload.username) if item.get("id") == assignment_id), None)
        title = str(task.get("title", "nhiệm vụ")) if task else "nhiệm vụ"
        subject = str(task.get("subject", "")) if task else ""
        background_tasks.add_task(
            send_web_push_to_user,
            payload.username,
            "Đã hoàn thành nhiệm vụ",
            f"Bạn đã hoàn thành: {title}.",
            "/student#assignments",
        )
        # Phụ huynh đã liên kết cũng nhận thông báo để theo dõi tiến độ.
        background_tasks.add_task(
            send_completion_notifications,
            payload.username,
            title,
            subject,
        )
    return {
        "message": "Đã cập nhật trạng thái nhiệm vụ.",
        "notification": {
            "title": "Đã hoàn thành nhiệm vụ" if payload.completed else "Đã mở lại nhiệm vụ",
            "message": "Tiến độ học tập đã được cập nhật trên StudySync.",
        },
    }


@app.delete("/api/assignments/{assignment_id}")
def delete_assignment(assignment_id: str, username: str = Query(...), authorization: str | None = Header(default=None)):
    _require_user_session(authorization, username, {"student"})
    if not StudyBus().delete_assignment(assignment_id, username):
        raise HTTPException(status_code=404, detail="Không tìm thấy nhiệm vụ.")
    _record_feature_success(username, authorization.partition(" ")[2] if authorization else None, "assignments")
    return {"message": "Đã xóa nhiệm vụ."}


@app.post("/api/parent/link-student")
def link_student(payload: ParentLinkPayload, authorization: str | None = Header(default=None)):
    _require_user_session(authorization, payload.parent_username, {"parent"})
    try:
        request = create_parent_link_request(payload.parent_username, payload.student_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_feature_success(payload.parent_username, authorization.partition(" ")[2] if authorization else None, "parent_link")
    return {
        "message": "Đã gửi yêu cầu liên kết. Học sinh cần xác nhận trong hộp thư.",
        "request": request,
    }


@app.get("/api/student/link-requests")
def student_link_requests(username: str = Query(...), authorization: str | None = Header(default=None)):
    student = _require_user_session(authorization, username, {"student"})
    if not student or student.get("role") != "student":
        raise HTTPException(status_code=404, detail="Không tìm thấy học sinh.")
    return {"requests": get_link_requests_for_student(username)}


@app.post("/api/student/link-requests/respond")
def respond_link_request(payload: LinkRequestResponsePayload, authorization: str | None = Header(default=None)):
    student = _require_user_session(authorization, payload.student_username, {"student"})
    if not student or student.get("role") != "student":
        raise HTTPException(status_code=404, detail="Không tìm thấy học sinh.")
    try:
        request = respond_to_parent_link_request(
            payload.student_username, payload.request_id, payload.accept
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.accept:
        _record_feature_success(payload.student_username, authorization.partition(" ")[2] if authorization else None, "parent_link")
    return {
        "message": "Đã xác nhận liên kết phụ huynh." if payload.accept else "Đã từ chối yêu cầu liên kết.",
        "request": request,
    }


@app.patch("/api/parent/student")
def update_parent_student(payload: StudentProfilePayload, authorization: str | None = Header(default=None)):
    _require_user_session(authorization, payload.parent_username, {"parent"})
    parent = get_user_by_username(payload.parent_username)
    if not parent or parent.get("role") != "parent":
        raise HTTPException(status_code=404, detail="Không tìm thấy phụ huynh.")
    try:
        student = update_linked_student(
            payload.parent_username,
            payload.student_id,
            payload.full_name,
            payload.class_name,
            payload.avatar,
            payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Đã cập nhật hồ sơ học sinh.", "student": student}


@app.get("/api/parent/children")
def parent_children(username: str = Query(...)):
    students = get_students_for_parent(username)
    return {"students": students}


@app.get("/api/profile")
def user_profile(username: str = Query(...), authorization: str | None = Header(default=None)):
    user = _require_user_session(authorization, username)
    return {"user": _public_user(user)}


def _public_user(user: dict) -> dict:
    return {key: user.get(key) for key in (
        "id", "username", "full_name", "role", "class_name", "student_id",
        "avatar", "parent_username", "is_active", "pin_login_enabled"
    )}

@app.patch("/api/profile")
def save_profile(payload: ProfileUpdatePayload, authorization: str | None = Header(default=None)):
    current_user = _require_user_session(authorization, payload.username)
    class_name = payload.class_name
    if get_username_bot_status()["enabled"] and current_user.get("role") == "student":
        name_valid, name_message = validate_display_name(payload.full_name)
        if not name_valid:
            raise HTTPException(status_code=400, detail=name_message)
        class_valid, class_result = validate_class_name(payload.class_name)
        if not class_valid:
            raise HTTPException(status_code=400, detail=class_result)
        class_name = class_result
    try:
        user = update_account(payload.username, full_name=payload.full_name,
                              class_name=class_name,
                              avatar=payload.avatar)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": _public_user(user)}

@app.post("/api/profile/password")
def change_password(payload: PasswordUpdatePayload, authorization: str | None = Header(default=None)):
    _require_user_session(authorization, payload.username)
    try:
        update_account(payload.username, current_password=payload.current_password,
                       new_password=payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Đã đổi mật khẩu. Vui lòng đăng nhập lại."}

@app.patch("/api/owner/users/{user_id}")
def owner_edit_user(user_id: str, payload: OwnerUserEditPayload, authorization: str | None = Header(default=None)):
    _require_owner(authorization)
    user = managed_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    class_name = str(user.get("class_name", "")) if payload.class_name is None else payload.class_name
    if get_username_bot_status()["enabled"] and user.get("role") == "student":
        name_valid, name_message = validate_display_name(payload.full_name)
        if not name_valid:
            raise HTTPException(status_code=400, detail=name_message)
        class_valid, class_result = validate_class_name(class_name)
        if not class_valid:
            raise HTTPException(status_code=400, detail=class_result)
        class_name = class_result
    try:
        updated = update_account(user["username"], full_name=payload.full_name,
                                 class_name=class_name, avatar=payload.avatar, by_owner=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": _public_user(updated)}

@app.patch("/api/owner/users/{user_id}/username")
def owner_rename_user(
    user_id: str, payload: OwnerUserRenamePayload, authorization: str | None = Header(default=None)
):
    """Cho phep quan tri doi ten dang nhap cho tai khoan bi canh bao.

    Giu nguyen id, lich hoc va bai tap; chi doi username va ho so.
    """
    _require_owner(authorization)
    user = managed_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")

    existing = [str(item.get("username", "")) for item in load_users()]
    target_username = str(payload.new_username or "").strip()
    if target_username.casefold() == str(user.get("username", "")).casefold():
        raise HTTPException(status_code=400, detail="Tên đăng nhập mới phải khác tên cũ.")

    full_name = str(user.get("full_name", "")) if payload.full_name is None else payload.full_name
    class_name = str(user.get("class_name", "")) if payload.class_name is None else payload.class_name

    if get_username_bot_status()["enabled"]:
        username_valid, username_message = validate_username(target_username)
        if not username_valid:
            raise HTTPException(
                status_code=400,
                detail=username_message,
                headers={"X-Username-Suggestions": ",".join(generate_suggested_username(
                    full_name, existing_usernames=existing,
                ))},
            )
        if user.get("role") == "student":
            name_valid, name_message = validate_display_name(full_name)
            if not name_valid:
                raise HTTPException(status_code=400, detail=name_message)
            class_valid, class_result = validate_class_name(class_name)
            if not class_valid:
                raise HTTPException(status_code=400, detail=class_result)
            class_name = class_result

    try:
        updated = rename_managed_user(
            str(user.get("username", "")), target_username, full_name, class_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": _public_user(updated)}


@app.patch("/api/owner/users/by-username/{username:path}/username")
def owner_rename_user_by_username(
    username: str, payload: OwnerUserRenamePayload, authorization: str | None = Header(default=None)
):
    """Đổi username theo tên hiện tại, tiện cho nút "Đổi tên hộ" trong trang admin."""
    _require_owner(authorization)
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    return owner_rename_user(str(user.get("id", "")), payload, authorization)


@app.post("/api/owner/username-bot/suggestions/{username:path}")
def owner_username_suggestions(username: str, authorization: str | None = Header(default=None)):
    _require_owner(authorization)
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    return {
        "suggestions": generate_suggested_username(
            str(user.get("full_name", "")),
            existing_usernames=[str(item.get("username", "")) for item in load_users()],
        ),
    }


@app.post("/api/reports", status_code=201)
def submit_report(payload: ReportPayload, authorization: str | None = Header(default=None)):
    _require_user_session(authorization, payload.username)
    try:
        return {"report": create_report(payload.username, payload.category, payload.message)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
@app.get("/api/owner/reports")
def owner_reports(authorization: str | None = Header(default=None)):
    _require_owner(authorization)
    return {"reports": list(reversed(list_reports()))}

@app.patch("/api/owner/reports/{report_id}")
def owner_mark_report(report_id: str, payload: ReportReadPayload, authorization: str | None = Header(default=None)):
    _require_owner(authorization)
    if not mark_report_read(report_id, payload.read):
        raise HTTPException(status_code=404, detail="Không tìm thấy báo cáo.")
    return {"message": "Đã cập nhật hòm thư."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=True)
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from auth_service import (
    authenticate_user,
    create_parent_link_request,
    get_link_requests_for_student,
    get_students_for_parent,
    get_user_by_username,
    register_user,
    respond_to_parent_link_request,
    set_secondary_pin,
    set_pin_login_enabled,
    update_linked_student,
    verify_secondary_pin,
)
from bus.study_bus import StudyBus

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="StudySync Unified App")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))


class AuthPayload(BaseModel):
    username: str
    password: str
    full_name: str | None = None
    role: str = "student"
    class_name: str | None = None
    pin: str | None = None


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


class ScheduleSlotDeletePayload(BaseModel):
    session: str
    day: str
    period: int


class AssignmentPayload(BaseModel):
    title: str
    subject: str
    due_date: date
    priority: str = "Trung bình"


class AssignmentCompletionPayload(BaseModel):
    completed: bool


class SecondaryPinSetupPayload(BaseModel):
    username: str
    password: str
    pin: str


class PinLoginSettingPayload(BaseModel):
    username: str
    password: str
    enabled: bool
    pin: str = ""


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
    tasks = study.assignments()
    if user.get("role") == "parent":
        students = get_students_for_parent(username)
        if not students:
            return []
        alerts: list[dict] = []
        stats = study.stats()
        for student in students:
            alerts.extend({
                "student": student.get("full_name") or student.get("username"),
                **alert,
            } for alert in _build_student_alerts(
                student.get("full_name") or student.get("username"),
                int(stats["completion_rate"]),
                tasks,
            ))
        return alerts[:10]
    stats = study.stats()
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


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


@app.get("/student")
async def student_dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="student_dashboard.html")


@app.get("/parent")
async def parent_dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="parent_dashboard.html")


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
    return {"message": "Đăng nhập thành công.", "user": sanitized}


@app.post("/api/auth/register")
def register(payload: AuthPayload):
    if payload.role.strip().lower() == "student" and not (payload.full_name or "").strip():
        raise HTTPException(status_code=400, detail="Họ tên không được để trống.")

    try:
        user = register_user(
            username=payload.username,
            password=payload.password,
            role=payload.role,
            full_name=payload.full_name or payload.username,
            class_name=payload.class_name or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
    return {"message": "Tạo tài khoản thành công.", "user": safe_user}


@app.get("/api/dashboard/student")
def student_dashboard(username: str = Query(...)):
    user = get_user_by_username(username)
    if not user or user.get("role") != "student":
        raise HTTPException(status_code=404, detail="Không tìm thấy học sinh.")

    study = StudyBus()
    tasks = study.assignments()
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
        "schedule": study.schedule(),
        "assignments": tasks,
        "alerts": alerts,
    }


@app.get("/api/notifications")
def notifications(username: str = Query(...)):
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")
    return {"notifications": _notifications_for_user(username)}


@app.post("/api/security/pin")
def setup_secondary_pin(payload: SecondaryPinSetupPayload):
    try:
        set_secondary_pin(payload.username, payload.password, payload.pin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Đã đăng ký mã PIN cấp 2."}


@app.post("/api/security/pin-login")
def update_pin_login_setting(payload: PinLoginSettingPayload):
    try:
        set_pin_login_enabled(payload.username, payload.password, payload.enabled, payload.pin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Đã cập nhật cài đặt PIN đăng nhập.", "enabled": payload.enabled}


@app.get("/api/dashboard/parent")
def parent_dashboard(username: str = Query(...)):
    parent = get_user_by_username(username)
    if not parent or parent.get("role") != "parent":
        raise HTTPException(status_code=404, detail="Không tìm thấy phụ huynh.")

    students = get_students_for_parent(username)

    study = StudyBus()
    tasks = study.assignments() if students else []
    completed_tasks = sum(1 for item in tasks if item.get("completed"))
    total_tasks = len(tasks)
    overall_completion = round(completed_tasks / total_tasks * 100) if total_tasks else 0

    student_rows = []
    for student in students:
        student_total = len(tasks)
        student_completed = min(completed_tasks, student_total)
        row_rate = round(student_completed / student_total * 100) if student_total else 0
        student_rows.append({
            "username": student.get("username"),
            "full_name": student.get("full_name"),
            "class_name": student.get("class_name", ""),
            "student_id": student.get("student_id", ""),
            "avatar": student.get("avatar", ""),
            "is_active": student.get("is_active", True),
            "completion_rate": row_rate,
            "alerts": _build_student_alerts(student.get("full_name") or student.get("username"), row_rate, tasks),
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
                "student_name": student_rows[0]["full_name"] if student_rows else "Học sinh",
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
def update_schedule_slot(payload: ScheduleSlotPayload):
    try:
        item = StudyBus().upsert_schedule_slot(
            payload.session, payload.day, payload.period, payload.subject, payload.lecturer
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Đã cập nhật thời khóa biểu.",
        "notification": {
            "title": "Đã cập nhật thời khóa biểu",
            "message": f"Đã lưu {item.get('subject', 'tiết học')} vào thứ {payload.day}, tiết {payload.period}.",
        },
        "schedule": item,
    }


@app.delete("/api/schedule/slot")
def delete_schedule_slot(payload: ScheduleSlotDeletePayload):
    deleted = StudyBus().delete_schedule_slot(payload.session, payload.day, payload.period)
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy tiết học.")
    return {"message": "Đã xóa tiết học."}


@app.post("/api/assignments")
def create_assignment(payload: AssignmentPayload):
    try:
        item = StudyBus().add_assignment(
            payload.title, payload.subject, payload.due_date, payload.priority
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Đã thêm nhiệm vụ.", "assignment": item}


@app.patch("/api/assignments/{assignment_id}")
def update_assignment(assignment_id: str, payload: AssignmentCompletionPayload):
    if not StudyBus().set_completed(assignment_id, payload.completed):
        raise HTTPException(status_code=404, detail="Không tìm thấy nhiệm vụ.")
    return {
        "message": "Đã cập nhật trạng thái nhiệm vụ.",
        "notification": {
            "title": "Đã hoàn thành nhiệm vụ" if payload.completed else "Đã mở lại nhiệm vụ",
            "message": "Tiến độ học tập đã được cập nhật trên StudySync.",
        },
    }


@app.delete("/api/assignments/{assignment_id}")
def delete_assignment(assignment_id: str):
    if not StudyBus().delete_assignment(assignment_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy nhiệm vụ.")
    return {"message": "Đã xóa nhiệm vụ."}


@app.post("/api/parent/link-student")
def link_student(payload: ParentLinkPayload):
    try:
        request = create_parent_link_request(payload.parent_username, payload.student_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Đã gửi yêu cầu liên kết. Học sinh cần xác nhận trong hộp thư.",
        "request": request,
    }


@app.get("/api/student/link-requests")
def student_link_requests(username: str = Query(...)):
    student = get_user_by_username(username)
    if not student or student.get("role") != "student":
        raise HTTPException(status_code=404, detail="Không tìm thấy học sinh.")
    return {"requests": get_link_requests_for_student(username)}


@app.post("/api/student/link-requests/respond")
def respond_link_request(payload: LinkRequestResponsePayload):
    student = get_user_by_username(payload.student_username)
    if not student or student.get("role") != "student":
        raise HTTPException(status_code=404, detail="Không tìm thấy học sinh.")
    try:
        request = respond_to_parent_link_request(
            payload.student_username, payload.request_id, payload.accept
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Đã xác nhận liên kết phụ huynh." if payload.accept else "Đã từ chối yêu cầu liên kết.",
        "request": request,
    }


@app.patch("/api/parent/student")
def update_parent_student(payload: StudentProfilePayload):
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
def user_profile(username: str = Query(...)):
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")
    return {"user": user}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=True)
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from auth_service import register_user  # noqa: E402
from backend.schedule_ocr import (  # noqa: E402
    TimetableImageError,
    _format_lecturer,
    _format_subject,
    _key,
    extract_timetable_slots,
    timetable_ocr_available,
)
from web_app import app  # noqa: E402

SAMPLE_IMAGE = ROOT / "tools" / "sample_timetable.png"
pytestmark = pytest.mark.skipif(
    not timetable_ocr_available(),
    reason="Máy chủ chưa cài rapidocr-onnxruntime và opencv.",
)


@pytest.fixture
def student_client(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr("web_app.get_username_bot_status", lambda: {"enabled": False})
    monkeypatch.setenv("STUDYSYNC_SESSION_SECRET", "test-session-secret-with-at-least-32-chars")
    register_user("student_ocr", "Pass1234", "student", "Học sinh OCR")
    from owner_auth import create_user_token

    token = create_user_token("student_ocr", "student")
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def test_day_keys_do_not_confuse_bay_with_ba():
    assert _key("THỨ BẢY") == "thubay"
    assert _key("Thứ Bảy") != _key("Thứ Ba")
    assert _key("THỨ BA") == "thuba"


def test_subject_and_lecturer_are_formatted_separately():
    # Giáo viên có tên gần giống môn học, không được gộp làm một.
    assert _format_subject("TOÁN") == "Toán"
    assert _format_lecturer("T.Hoàn") == "T.Hoàn"
    assert _format_subject("NGU' VÃN") == "Ngữ văn"
    assert _format_subject("LICH SUr") == "Lịch sử"


def test_empty_image_reports_clear_error():
    with pytest.raises(TimetableImageError):
        extract_timetable_slots(b"khong-phai-anh")


def test_day_headers_are_not_read_as_lessons():
    """Ảnh thật có dòng tiêu đề Thứ 2 → Thứ 7, không được thành tiết học."""
    slots, _ = extract_timetable_slots(SAMPLE_IMAGE.read_bytes())

    assert all(slot["subject"] not in {"THU2", "THU3", "THU4", "THU5", "THU6", "THU7"} for slot in slots)


def test_session_split_keeps_both_tables_apart():
    """Ảnh thật chỉ ghi nhãn 'Buổi chiều' ở bảng dưới, bảng trên là buổi sáng."""
    slots, _ = extract_timetable_slots(SAMPLE_IMAGE.read_bytes())

    assert any(slot["session"] == "morning" for slot in slots)
    assert any(slot["session"] == "afternoon" for slot in slots)
    # Tên môn được chuẩn hoá về dạng có dấu.
    morning = {slot["subject"] for slot in slots if slot["session"] == "morning"}
    afternoon = {slot["subject"] for slot in slots if slot["session"] == "afternoon"}
    assert "Toán" in morning
    assert "TAGT" in afternoon
    # Môn chỉ xuất hiện ở buổi sáng.
    assert "GDTC" not in afternoon
    assert "STEM" not in afternoon
    # Môn thực hành chỉ xuất hiện ở buổi chiều.
    assert "ISMART" not in morning
    assert "TAGT" not in morning


def test_two_line_cells_split_into_subject_and_lecturer():
    """Ô viết hai dòng như TAGT/TAGT8 phải tách đúng, không gộp thành tiết."""
    slots, _ = extract_timetable_slots(SAMPLE_IMAGE.read_bytes())

    tagt = [slot for slot in slots if slot["subject"] == "TAGT"]
    assert len(tagt) == 2
    assert {(slot["day"], slot["period"]) for slot in tagt} == {("2", 1), ("2", 2)}
    assert all(slot["lecturer"] == "TAGT8" for slot in tagt)
    # Ô viết trên hai dòng "HDTN-SHDC" / "L.M.Thành" phải giữ nguyên dấu
    # gạch trong tên môn, không được cắt thành "HDTN" và "SHDC".
    hdtn = [slot for slot in slots if slot["subject"].startswith("HDTN")]
    assert {slot["subject"] for slot in hdtn} == {"HDTN-SHDC", "HDTN-CĐ", "HDTN-SHL"}
    lecturers = {slot["subject"]: slot["lecturer"] for slot in hdtn}
    assert lecturers == {
        "HDTN-SHDC": "L. M.Thanh",
        "HDTN-CĐ": "L.M.Thanh",
        "HDTN-SHL": "L. M.Thanh",
    }


def test_empty_rows_still_count_as_periods():
    """Hàng trống giữa các tiết không làm lệch số thứ tự tiết."""
    slots, _ = extract_timetable_slots(SAMPLE_IMAGE.read_bytes())
    morning = [slot for slot in slots if slot["session"] == "morning"]
    afternoon = [slot for slot in slots if slot["session"] == "afternoon"]

    # Ảnh thật có 5 tiết sáng và 4 tiết chiều có nội dung.
    assert {slot["period"] for slot in morning} == {1, 2, 3, 4, 5}
    assert {slot["period"] for slot in afternoon} == {1, 2, 3}
    assert max(slot["period"] for slot in afternoon) == 3


def test_periods_beyond_five_are_kept():
    """TKB thật có tiết 6, hệ thống phải lưu được thay vì cắt bỏ."""
    from database.study_repository import MAX_PERIOD
    from backend.schedule_ocr import MAX_PERIODS_PER_SESSION

    assert MAX_PERIODS_PER_SESSION == MAX_PERIOD >= 6
    assert MAX_PERIOD >= 6


def test_six_period_image_reports_warning_when_truncated():
    """Nếu ảnh dài hơn giới hạn thì phải cảnh báo, không âm thầm mất tiết."""
    from backend import schedule_ocr

    slots, warnings = schedule_ocr.extract_timetable_slots(
        SAMPLE_IMAGE.read_bytes(), max_periods_per_session=2
    )

    assert max(slot["period"] for slot in slots) <= 2
    assert warnings and "tiết" in warnings[0]


def test_extracts_timetable_grid_from_image():
    slots, _ = extract_timetable_slots(SAMPLE_IMAGE.read_bytes())

    grid = {(slot["session"], slot["day"], slot["period"]): slot for slot in slots}
    # Ảnh có 25 tiết sáng và 14 tiết chiều, ô trống không tạo ra tiết.
    assert len(slots) == 39
    assert grid[("morning", "2", 1)]["subject"] == "HDTN-SHDC"
    assert grid[("morning", "2", 1)]["lecturer"] == "L. M.Thanh"
    # Cột Thứ 7 trống hoàn toàn ở cả hai buổi nên không tạo ra tiết nào.
    assert all(day != "7" for _, day, _ in grid)
    # Buổi chiều tiết 1 Thứ 4 là Toán, giáo viên viết không dấu trên ảnh.
    assert grid[("afternoon", "4", 1)]["subject"] == "Toán"
    assert grid[("afternoon", "4", 1)]["lecturer"] == "T.Hoang"
    # Ảnh mẫu có Toán ở buổi chiều, tiết 1, cột Thứ 6.
    assert grid[("afternoon", "6", 1)]["subject"] == "Toán"


def test_import_endpoint_requires_student_session(student_client):
    client, _ = student_client
    response = client.post(
        "/api/schedule/import-image",
        files={"file": ("tkb.png", SAMPLE_IMAGE.read_bytes(), "image/png")},
    )

    # Không có phiên thì tài khoản không tồn tại nên bị chặn 403.
    assert response.status_code == 403


def test_import_endpoint_rejects_other_account(student_client):
    client, headers = student_client
    response = client.post(
        "/api/schedule/import-image",
        headers={**headers, "X-Username": "nguoi_khac"},
        files={"file": ("tkb.png", SAMPLE_IMAGE.read_bytes(), "image/png")},
    )

    assert response.status_code == 403


def test_import_endpoint_returns_slots_for_review(student_client):
    client, headers = student_client
    response = client.post(
        "/api/schedule/import-image",
        headers={**headers, "X-Username": "student_ocr"},
        files={"file": ("tkb.png", SAMPLE_IMAGE.read_bytes(), "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert "Đã đọc" in data["message"]
    assert data["slots"]
    assert data["warnings"] == []
    assert all(slot["username"] == "student_ocr" for slot in data["slots"])
    assert {"session", "day", "period", "subject", "lecturer", "username"} == set(data["slots"][0])


def test_import_endpoint_does_not_write_schedule(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr("web_app.get_username_bot_status", lambda: {"enabled": False})
    monkeypatch.setattr("database.study_repository.data_file", lambda name: tmp_path / name)
    monkeypatch.setenv("STUDYSYNC_SESSION_SECRET", "test-session-secret-with-at-least-32-chars")
    register_user("student_ocr", "Pass1234", "student", "Học sinh OCR")
    from bus.study_bus import StudyBus
    from owner_auth import create_user_token

    token = create_user_token("student_ocr", "student")
    client = TestClient(app)

    response = client.post(
        "/api/schedule/import-image",
        headers={"Authorization": f"Bearer {token}", "X-Username": "student_ocr"},
        files={"file": ("tkb.png", SAMPLE_IMAGE.read_bytes(), "image/png")},
    )

    assert response.status_code == 200
    # Đọc ảnh chỉ xem trước, người dùng phải bấm Lưu mới ghi vào thời khóa biểu.
    assert StudyBus().schedule("student_ocr") == []


def test_import_status_endpoint_reports_availability():
    client = TestClient(app)
    response = client.get("/api/schedule/import-image/status")

    assert response.status_code == 200
    assert response.json()["available"] is True


def test_broken_image_returns_friendly_message(student_client):
    client, headers = student_client
    response = client.post(
        "/api/schedule/import-image",
        headers={**headers, "X-Username": "student_ocr"},
        files={"file": ("tkb.png", b"day la du lieu khong phai anh", "image/png")},
    )

    assert response.status_code == 422
    assert "ảnh" in response.json()["detail"].lower()

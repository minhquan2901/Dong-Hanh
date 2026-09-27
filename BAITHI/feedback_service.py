# Persistent inbox for user bug reports and feedback."
from __future__ import annotations
import json
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
from data_storage import data_file, write_json_atomic
INBOX_FILE = data_file("feedback_inbox.json")
INBOX_LOCK = RLock()


def list_reports() -> list[dict]:
    with INBOX_LOCK:
        if not INBOX_FILE.exists():
            return []
        try:
            items = json.loads(INBOX_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Không đọc được hòm thư góp ý.") from exc
        if not isinstance(items, list):
            raise RuntimeError("Dữ liệu hòm thư không hợp lệ.")
        return items

def create_report(username: str, category: str, message: str) -> dict:
    if category not in {"bug", "feedback"}:
        raise ValueError("Loại báo cáo không hợp lệ.")
    text = message.strip()
    if not 10 <= len(text) <= 2000:
        raise ValueError("Nội dung cần từ 10 đến 2000 ký tự.")
    with INBOX_LOCK:
        items = list_reports()
        report = {
            "id": uuid4().hex, "username": username, "category": category,
            "message": text, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "read": False,
        }
        items.append(report)
        write_json_atomic(INBOX_FILE, items)
        return report

def mark_report_read(report_id: str, read: bool) -> bool:
    with INBOX_LOCK:
        items = list_reports()
        for item in items:
            if item.get("id") == report_id:
                item["read"] = read
                write_json_atomic(INBOX_FILE, items)
                return True
        return False

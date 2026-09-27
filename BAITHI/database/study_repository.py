from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class StudyRepository:
    """Lưu thời khóa biểu và bài tập trong SQLite, với fallback về JSON cho tương thích."""

    def __init__(
        self,
        file_path: str | Path | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        root = Path(__file__).resolve().parent.parent
        self.file_path = Path(file_path or root / "data" / "study_data.json")
        self.db_path = Path(db_path or root / "data" / "studysync.db")
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._migrate_json_file_if_needed()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule (
                    id TEXT PRIMARY KEY,
                    session TEXT,
                    day TEXT,
                    period INTEGER,
                    subject TEXT,
                    lecturer TEXT,
                    reminder_minutes INTEGER DEFAULT 30,
                    start TEXT DEFAULT '',
                    room TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assignments (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    subject TEXT,
                    due_date TEXT,
                    priority TEXT,
                    completed INTEGER DEFAULT 0
                )
                """
            )

    def _migrate_json_file_if_needed(self) -> None:
        with self._connect() as conn:
            schedule_count = conn.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]
            assignment_count = conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
            if schedule_count or assignment_count:
                return
            if not self.file_path.exists():
                return
            try:
                data = json.loads(self.file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return
            if not isinstance(data, dict):
                return
            for item in data.get("schedule", []):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO schedule (id, session, day, period, subject, lecturer, reminder_minutes, start, room)
                    VALUES (:id, :session, :day, :period, :subject, :lecturer, :reminder_minutes, :start, :room)
                    """,
                    {
                        "id": item.get("id") or datetime.now().strftime("lesson-%Y%m%d%H%M%S%f"),
                        "session": item.get("session", "morning"),
                        "day": str(item.get("day", "2")),
                        "period": int(item.get("period", 1)),
                        "subject": item.get("subject", ""),
                        "lecturer": item.get("lecturer", ""),
                        "reminder_minutes": int(item.get("reminder_minutes", 30)),
                        "start": item.get("start", ""),
                        "room": item.get("room", ""),
                    },
                )
            for item in data.get("assignments", []):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO assignments (id, title, subject, due_date, priority, completed)
                    VALUES (:id, :title, :subject, :due_date, :priority, :completed)
                    """,
                    {
                        "id": item.get("id") or datetime.now().strftime("task-%Y%m%d%H%M%S%f"),
                        "title": item.get("title", ""),
                        "subject": item.get("subject", ""),
                        "due_date": item.get("due_date", ""),
                        "priority": item.get("priority", "Trung bình"),
                        "completed": 1 if item.get("completed") else 0,
                    },
                )

    def _new_schedule_id(self) -> str:
        return f"lesson-{uuid4().hex}"

    def _read(self) -> dict[str, list[dict[str, Any]]]:
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    "schedule": data.get("schedule", []),
                    "assignments": data.get("assignments", []),
                }
        except (OSError, json.JSONDecodeError):
            pass
        return {"schedule": [], "assignments": []}

    def _write(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_schedule(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM schedule ORDER BY day, period, session"
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_schedule_slot(
        self,
        session: str,
        day: str,
        period: int,
        subject: str,
        lecturer: str,
    ) -> dict[str, Any]:
        return self.upsert_schedule_slots([
            {
                "session": session,
                "day": day,
                "period": period,
                "subject": subject,
                "lecturer": lecturer,
            }
        ])[0]

    def upsert_schedule_slots(self, slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(slots, list):
            raise ValueError("Danh sách tiết học không hợp lệ.")

        created: list[dict[str, Any]] = []
        with self._connect() as conn:
            for raw_slot in slots:
                session = str(raw_slot.get("session", "morning")).strip()
                day = str(raw_slot.get("day", "2")).strip()
                period = int(raw_slot.get("period", 1))
                subject = str(raw_slot.get("subject", "")).strip()
                lecturer = str(raw_slot.get("lecturer", "")).strip()

                if session not in {"morning", "afternoon"}:
                    raise ValueError("Buổi học không hợp lệ.")
                if day not in {"2", "3", "4", "5", "6", "7"}:
                    raise ValueError("Thứ học không hợp lệ.")
                if period not in range(1, 6):
                    raise ValueError("Tiết học phải từ 1 đến 5.")
                if not subject:
                    raise ValueError("Tên môn học không được để trống.")

                row = conn.execute(
                    "SELECT * FROM schedule WHERE session=? AND day=? AND period=?",
                    (session, day, period),
                ).fetchone()
                if row:
                    conn.execute(
                        "UPDATE schedule SET subject=?, lecturer=? WHERE id=?",
                        (subject, lecturer, row["id"]),
                    )
                    item = dict(row)
                    item.update({"subject": subject, "lecturer": lecturer})
                    created.append(item)
                    continue

                item = {
                    "id": self._new_schedule_id(),
                    "session": session,
                    "day": day,
                    "period": period,
                    "subject": subject,
                    "lecturer": lecturer,
                    "reminder_minutes": 30,
                    "start": "",
                    "room": "",
                }
                conn.execute(
                    "INSERT INTO schedule (id, session, day, period, subject, lecturer, reminder_minutes, start, room) VALUES (:id, :session, :day, :period, :subject, :lecturer, :reminder_minutes, :start, :room)",
                    item,
                )
                created.append(item)
            conn.commit()
        return created

    def delete_schedule_slot(self, session: str, day: str, period: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM schedule WHERE session=? AND day=? AND period=?",
                (session, str(day), int(period)),
            )
            conn.commit()
            return cursor.rowcount > 0

    def add_schedule(
        self,
        subject: str,
        day: str,
        start: str,
        room: str,
        lecturer: str,
        reminder_minutes: int,
    ) -> dict[str, Any]:
        item = {
            "id": self._new_schedule_id(),
            "subject": subject,
            "day": day,
            "start": start,
            "room": room,
            "lecturer": lecturer,
            "reminder_minutes": reminder_minutes,
            "session": "morning",
            "period": 1,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO schedule (id, session, day, period, subject, lecturer, reminder_minutes, start, room) VALUES (:id, :session, :day, :period, :subject, :lecturer, :reminder_minutes, :start, :room)",
                item,
            )
            conn.commit()
        return item

    def get_assignments(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM assignments ORDER BY due_date"
            ).fetchall()
        assignments = [dict(row) for row in rows]
        for item in assignments:
            item["completed"] = bool(item.get("completed"))
        return assignments

    def add_assignment(self, title: str, subject: str, due_date: str, priority: str) -> dict[str, Any]:
        item = {
            "id": datetime.now().strftime("task-%Y%m%d%H%M%S%f"),
            "title": title,
            "subject": subject,
            "due_date": due_date,
            "priority": priority,
            "completed": 0,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO assignments (id, title, subject, due_date, priority, completed) VALUES (:id, :title, :subject, :due_date, :priority, :completed)",
                item,
            )
            conn.commit()
        item["completed"] = False
        return item

    def set_assignment_completed(self, assignment_id: str, completed: bool) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE assignments SET completed=? WHERE id=?",
                (1 if completed else 0, assignment_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_assignment(self, assignment_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM assignments WHERE id=?",
                (assignment_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

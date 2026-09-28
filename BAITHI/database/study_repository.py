from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from data_storage import data_file
from db import is_postgres
from uuid import uuid4


class StudyRepository:
    """Lưu thời khóa biểu và bài tập.

    Dùng SQLite khi chạy local/test, dùng bảng riêng trong Postgres khi deploy.
    Cả hai đều giữ cùng tên cột nên các hàm bên dưới không cần đổi.
    """

    def __init__(
        self,
        file_path: str | Path | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        self.file_path = Path(file_path) if file_path is not None else data_file("study_data.json")
        self.db_path = Path(db_path) if db_path is not None else data_file("studysync.db")
        self._lock = threading.RLock()
        if not is_postgres():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._migrate_json_file_if_needed()

    # --- Kết nối ---------------------------------------------------------
    def _postgres_connection(self):
        from db import _init_pool

        return _init_pool().connection()

    def _connect(self):
        if is_postgres():
            return self._postgres_connection()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _count(self, conn, table: str) -> int:
        row = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
        if row is None:
            return 0
        if isinstance(row, dict):
            return int(row.get("total", 0))
        return int(row[0])

    def _rows_to_dicts(self, rows: list[Any]) -> list[dict[str, Any]]:
        """psycopg3 tra ve dict; sqlite3 tra ve sqlite3.Row."""
        result = []
        for row in rows:
            if isinstance(row, dict):
                result.append(row)
            elif isinstance(row, sqlite3.Row):
                result.append(dict(row))
            else:
                result.append(dict(row))
        return result

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            if is_postgres():
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schedule (
                        id TEXT PRIMARY KEY,
                        owner_username TEXT NOT NULL DEFAULT '',
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
                        owner_username TEXT NOT NULL DEFAULT '',
                        title TEXT,
                        subject TEXT,
                        due_date TEXT,
                        priority TEXT,
                        completed INTEGER DEFAULT 0
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS schedule_owner_slot_idx "
                    "ON schedule(owner_username, session, day, period)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS assignments_owner_due_idx "
                    "ON assignments(owner_username, due_date)"
                )
                conn.commit()
                return
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule (
                    id TEXT PRIMARY KEY,
                    owner_username TEXT NOT NULL DEFAULT '',
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
                    owner_username TEXT NOT NULL DEFAULT '',
                    title TEXT,
                    subject TEXT,
                    due_date TEXT,
                    priority TEXT,
                    completed INTEGER DEFAULT 0
                )
                """
            )
            for table in ("schedule", "assignments"):
                columns = {
                    row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
                if "owner_username" not in columns:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN owner_username TEXT NOT NULL DEFAULT ''"
                    )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS schedule_owner_slot_idx "
                "ON schedule(owner_username, session, day, period)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS assignments_owner_due_idx "
                "ON assignments(owner_username, due_date)"
            )
            legacy_owner = os.environ.get("LEGACY_STUDY_OWNER_USERNAME", "").strip()
            if legacy_owner:
                conn.execute(
                    "UPDATE schedule SET owner_username=? WHERE owner_username=''",
                    (legacy_owner,),
                )
                conn.execute(
                    "UPDATE assignments SET owner_username=? WHERE owner_username=''",
                    (legacy_owner,),
                )

    def _insert_schedule_row(self, conn, item: dict[str, Any]) -> None:
        columns = "id, owner_username, session, day, period, subject, lecturer, reminder_minutes, start, room"
        if is_postgres():
            values = [item["id"], item["owner_username"], item["session"], item["day"], item["period"], item["subject"], item["lecturer"], item["reminder_minutes"], item["start"], item["room"]]
            placeholders = ", ".join(["%s"] * 10)
            statement = (
                f"INSERT INTO schedule ({columns}) VALUES ({placeholders}) "
                "ON CONFLICT (id) DO UPDATE SET subject=EXCLUDED.subject, "
                "lecturer=EXCLUDED.lecturer, owner_username=EXCLUDED.owner_username"
            )
            conn.execute(statement, values)
            return
        placeholders = ":" + ", :".join(columns.replace(" ", "").split(","))
        statement = f"INSERT OR REPLACE INTO schedule ({columns}) VALUES ({placeholders})"
        conn.execute(statement, item)

    def _insert_assignment_row(self, conn, item: dict[str, Any]) -> None:
        columns = "id, owner_username, title, subject, due_date, priority, completed"
        if is_postgres():
            values = [item["id"], item["owner_username"], item["title"], item["subject"], item["due_date"], item["priority"], item["completed"]]
            placeholders = ", ".join(["%s"] * 7)
            statement = (
                f"INSERT INTO assignments ({columns}) VALUES ({placeholders}) "
                "ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, "
                "subject=EXCLUDED.subject, due_date=EXCLUDED.due_date, "
                "priority=EXCLUDED.priority, completed=EXCLUDED.completed"
            )
            conn.execute(statement, values)
            return
        placeholders = ":" + ", :".join(columns.replace(" ", "").split(","))
        statement = f"INSERT OR REPLACE INTO assignments ({columns}) VALUES ({placeholders})"
        conn.execute(statement, item)

    def _to_sqlite_style(self, sql: str, params: dict[str, Any]) -> tuple[str, list[Any]]:
        """Doi tham so dang ten (:ten) sang tham so vi tri (%s) cho Postgres."""
        statement = sql
        values: list[Any] = []
        for name, value in params.items():
            statement = statement.replace(f":{name}", "%s")
            values.append(value)
        return statement, values

    def _query(self, conn, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Chay truy van tra ve duoc hang, doc duoc tren ca SQLite va Postgres."""
        if is_postgres():
            statement, values = self._to_sqlite_style(sql, params)
            cursor = conn.execute(statement, values)
            if cursor.description is None:
                return []
            return self._rows_to_dicts(cursor.fetchall())
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def _run(self, conn, sql: str, params: dict[str, Any]) -> int:
        """Chay lenh INSERT/UPDATE/DELETE, tra ve so dong bi anh huong."""
        if is_postgres():
            statement, values = self._to_sqlite_style(sql, params)
            cursor = conn.execute(statement, values)
            return cursor.rowcount
        cursor = conn.execute(sql, params)
        return cursor.rowcount

    def _migrate_json_file_if_needed(self) -> None:
        with self._lock, self._connect() as conn:
            schedule_count = self._count(conn, "schedule")
            assignment_count = self._count(conn, "assignments")
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
                self._insert_schedule_row(conn, {
                    "id": item.get("id") or datetime.now().strftime("lesson-%Y%m%d%H%M%S%f"),
                    "owner_username": str(
                        item.get("owner_username") or os.environ.get("LEGACY_STUDY_OWNER_USERNAME", "")
                    ).strip().lower(),
                    "session": item.get("session", "morning"),
                    "day": str(item.get("day", "2")),
                    "period": int(item.get("period", 1)),
                    "subject": item.get("subject", ""),
                    "lecturer": item.get("lecturer", ""),
                    "reminder_minutes": int(item.get("reminder_minutes", 30)),
                    "start": item.get("start", ""),
                    "room": item.get("room", ""),
                })
            for item in data.get("assignments", []):
                self._insert_assignment_row(conn, {
                    "id": item.get("id") or datetime.now().strftime("task-%Y%m%d%H%M%S%f"),
                    "owner_username": str(
                        item.get("owner_username") or os.environ.get("LEGACY_STUDY_OWNER_USERNAME", "")
                    ).strip().lower(),
                    "title": item.get("title", ""),
                    "subject": item.get("subject", ""),
                    "due_date": item.get("due_date", ""),
                    "priority": item.get("priority", "Trung bình"),
                    "completed": 1 if item.get("completed") else 0,
                })

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

    def get_schedule(self, username: str | None) -> list[dict[str, Any]]:
        owner_username = str(username or "").strip().lower()
        if not owner_username:
            return []
        with self._lock, self._connect() as conn:
            rows = self._query(
                conn,
                "SELECT * FROM schedule WHERE owner_username=:owner ORDER BY day, period, session",
                {"owner": owner_username},
            )
        return rows

    def upsert_schedule_slot(
        self,
        session: str,
        day: str,
        period: int,
        subject: str,
        lecturer: str,
        username: str,
    ) -> dict[str, Any]:
        return self.upsert_schedule_slots([
            {
                "session": session,
                "day": day,
                "period": period,
                "subject": subject,
                "lecturer": lecturer,
                "username": username,
            }
        ])[0]

    def upsert_schedule_slots(self, slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(slots, list):
            raise ValueError("Danh sách tiết học không hợp lệ.")

        created: list[dict[str, Any]] = []
        with self._lock, self._connect() as conn:
            for raw_slot in slots:
                session = str(raw_slot.get("session", "morning")).strip()
                day = str(raw_slot.get("day", "2")).strip()
                period = int(raw_slot.get("period", 1))
                subject = str(raw_slot.get("subject", "")).strip()
                lecturer = str(raw_slot.get("lecturer", "")).strip()
                owner_username = str(raw_slot.get("username", "")).strip().lower()

                if not owner_username:
                    raise ValueError("Không xác định được tài khoản sở hữu thời khóa biểu.")

                if session not in {"morning", "afternoon"}:
                    raise ValueError("Buổi học không hợp lệ.")
                if day not in {"2", "3", "4", "5", "6", "7"}:
                    raise ValueError("Thứ học không hợp lệ.")
                if period not in range(1, 6):
                    raise ValueError("Tiết học phải từ 1 đến 5.")
                if not subject:
                    raise ValueError("Tên môn học không được để trống.")

                existing = self._query(
                    conn,
                    "SELECT * FROM schedule WHERE owner_username=:owner AND session=:session AND day=:day AND period=:period",
                    {"owner": owner_username, "session": session, "day": day, "period": period},
                )
                if existing:
                    row = existing[0]
                    self._run(
                        conn,
                        "UPDATE schedule SET subject=:subject, lecturer=:lecturer WHERE id=:id",
                        {"subject": subject, "lecturer": lecturer, "id": row["id"]},
                    )
                    item = dict(row)
                    item.update({"subject": subject, "lecturer": lecturer})
                    created.append(item)
                    continue

                item = {
                    "id": self._new_schedule_id(),
                    "owner_username": owner_username,
                    "session": session,
                    "day": day,
                    "period": period,
                    "subject": subject,
                    "lecturer": lecturer,
                    "reminder_minutes": 30,
                    "start": "",
                    "room": "",
                }
                self._insert_schedule_row(conn, item)
                created.append(item)
            if is_postgres():
                conn.commit()
        return created

    def delete_schedule_slot(self, session: str, day: str, period: int, username: str) -> bool:
        owner_username = str(username or "").strip().lower()
        if not owner_username:
            return False
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM schedule WHERE owner_username=%s AND session=%s AND day=%s AND period=%s"
                if is_postgres() else
                "DELETE FROM schedule WHERE owner_username=? AND session=? AND day=? AND period=?",
                (owner_username, session, str(day), int(period)),
            )
            if is_postgres():
                conn.commit()
            return cursor.rowcount > 0

    def delete_user_data(self, username: str) -> None:
        owner_username = str(username or "").strip().lower()
        if not owner_username:
            return
        with self._lock, self._connect() as conn:
            if is_postgres():
                conn.execute("DELETE FROM schedule WHERE owner_username=%s", (owner_username,))
                conn.execute("DELETE FROM assignments WHERE owner_username=%s", (owner_username,))
                conn.commit()
            else:
                conn.execute("DELETE FROM schedule WHERE owner_username=?", (owner_username,))
                conn.execute("DELETE FROM assignments WHERE owner_username=?", (owner_username,))

    def add_schedule(
        self,
        subject: str,
        day: str,
        start: str,
        room: str,
        lecturer: str,
        reminder_minutes: int,
        username: str,
    ) -> dict[str, Any]:
        item = {
            "id": self._new_schedule_id(),
            "owner_username": str(username or "").strip().lower(),
            "subject": subject,
            "day": day,
            "start": start,
            "room": room,
            "lecturer": lecturer,
            "reminder_minutes": reminder_minutes,
            "session": "morning",
            "period": 1,
        }
        with self._lock, self._connect() as conn:
            self._insert_schedule_row(conn, item)
            if is_postgres():
                conn.commit()
        return item

    def get_assignments(self, username: str | None) -> list[dict[str, Any]]:
        owner_username = str(username or "").strip().lower()
        if not owner_username:
            return []
        with self._lock, self._connect() as conn:
            rows = self._query(
                conn,
                "SELECT * FROM assignments WHERE owner_username=:owner ORDER BY due_date",
                {"owner": owner_username},
            )
        assignments = [dict(row) for row in rows]
        for item in assignments:
            item["completed"] = bool(item.get("completed"))
        return assignments

    def add_assignment(self, title: str, subject: str, due_date: str, priority: str, username: str) -> dict[str, Any]:
        item = {
            "id": f"task-{uuid4().hex}",
            "owner_username": str(username or "").strip().lower(),
            "title": title,
            "subject": subject,
            "due_date": due_date,
            "priority": priority,
            "completed": 0,
        }
        with self._lock, self._connect() as conn:
            self._insert_assignment_row(conn, item)
            if is_postgres():
                conn.commit()
        item["completed"] = False
        return item

    def set_assignment_completed(self, assignment_id: str, completed: bool, username: str) -> bool:
        owner_username = str(username or "").strip().lower()
        if not owner_username:
            return False
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE assignments SET completed=%s WHERE id=%s AND owner_username=%s"
                if is_postgres() else
                "UPDATE assignments SET completed=? WHERE id=? AND owner_username=?",
                (1 if completed else 0, assignment_id, owner_username),
            )
            if is_postgres():
                conn.commit()
            return cursor.rowcount > 0

    def delete_assignment(self, assignment_id: str, username: str) -> bool:
        owner_username = str(username or "").strip().lower()
        if not owner_username:
            return False
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM assignments WHERE id=%s AND owner_username=%s"
                if is_postgres() else
                "DELETE FROM assignments WHERE id=? AND owner_username=?",
                (assignment_id, owner_username),
            )
            if is_postgres():
                conn.commit()
            return cursor.rowcount > 0

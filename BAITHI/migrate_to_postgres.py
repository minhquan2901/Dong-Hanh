"""Đưa dữ liệu đang có trên máy lên Neon/Postgres.

Cách dùng (chạy một lần duy nhất, trước khi deploy bản dùng database):

    # 1. Lấy chuỗi kết nối từ Neon Console > Connection Details
    # 2. Đặt biến môi trường
    $env:STUDYSYNC_DATABASE_URL = "postgresql://user:pass@ep-xxx.neon.tech/studysync?sslmode=require"
    # 3. Chạy
    .\.venv\Scripts\python.exe migrate_to_postgres.py

Script chỉ ghi dữ liệu chưa có trên Neon, không ghi đè bản đang chạy trên web.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

DOCUMENT_KEYS = (
    "users",
    "link_requests",
    "feedback_inbox",
    "feature_usage",
)


def read_json(filename: str) -> Any:
    path = DATA_DIR / filename
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  ! Bo qua {filename}: khong doc duoc ({exc})")
        return None


def read_study_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    db_path = DATA_DIR / "studysync.db"
    if not db_path.is_file():
        return [], []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        schedule = [dict(row) for row in conn.execute("SELECT * FROM schedule").fetchall()]
        assignments = [dict(row) for row in conn.execute("SELECT * FROM assignments").fetchall()]
    finally:
        conn.close()
    return schedule, assignments


def main() -> int:
    database_url = os.environ.get("STUDYSYNC_DATABASE_URL", "").strip()
    if not database_url:
        print("Chua dat STUDYSYNC_DATABASE_URL. Xem huong dan tren dau file.")
        return 1

    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ImportError:
        print("Thieu psycopg. Chay: pip install \"psycopg[binary]\" \"psycopg-pool\"")
        return 1

    pool = ConnectionPool(database_url, min_size=1, max_size=2, open=True)
    with pool.connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS studysync_documents (
                key TEXT PRIMARY KEY,
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule (
                id TEXT PRIMARY KEY,
                owner_username TEXT NOT NULL DEFAULT '',
                session TEXT, day TEXT, period INTEGER,
                subject TEXT, lecturer TEXT,
                reminder_minutes INTEGER DEFAULT 30,
                start TEXT DEFAULT '', room TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assignments (
                id TEXT PRIMARY KEY,
                owner_username TEXT NOT NULL DEFAULT '',
                title TEXT, subject TEXT, due_date TEXT, priority TEXT,
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

        print("Dang tai len Neon...")

        for key in DOCUMENT_KEYS:
            payload = read_json(f"{key}.json")
            if payload is None:
                print(f"  - {key}: khong co du lieu local, bo qua")
                continue
            exists = conn.execute(
                "SELECT 1 FROM studysync_documents WHERE key=%s", (key,)
            ).fetchone()
            if exists is not None:
                print(f"  - {key}: da co tren Neon, giu nguyen (khong ghi de)")
                continue
            conn.execute(
                "INSERT INTO studysync_documents (key, payload) VALUES (%s, %s)",
                (key, json.dumps(payload, ensure_ascii=False)),
            )
            count = len(payload.get("users", [])) if isinstance(payload, dict) else len(payload)
            print(f"  + {key}: da tai {count} ban ghi")

        schedule, assignments = read_study_rows()
        for table, rows in (("schedule", schedule), ("assignments", assignments)):
            if not rows:
                print(f"  - {table}: khong co du lieu local, bo qua")
                continue
            existing = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if existing:
                print(f"  - {table}: da co {existing} dong tren Neon, giu nguyen (khong ghi de)")
                continue
            columns = list(rows[0].keys())
            placeholders = ", ".join(["%s"] * len(columns))
            statement = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
            for row in rows:
                conn.execute(statement, [row[name] for name in columns])
            print(f"  + {table}: da tai {len(rows)} dong")

        conn.commit()

        print("\nKet qua tren Neon:")
        for key in DOCUMENT_KEYS:
            row = conn.execute(
                "SELECT payload FROM studysync_documents WHERE key=%s", (key,)
            ).fetchone()
            if row is None:
                print(f"  {key}: rong")
                continue
            payload = row[0]
            count = len(payload.get("users", [])) if isinstance(payload, dict) else len(payload)
            print(f"  {key}: {count} ban ghi")
        for table in ("schedule", "assignments"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count} dong")

    pool.close()
    print("\nXong. Bay gio dat STUDYSYNC_DATABASE_URL tren Render roi deploy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

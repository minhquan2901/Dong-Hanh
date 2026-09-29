"""Lớp trừu tượng lưu trữ dữ liệu: dùng file JSON khi chạy local, Postgres khi deploy.

Chọn nguồn lưu trữ theo biến môi trường:
  - Có STUDYSYNC_DATABASE_URL (chuỗi kết nối Postgres) thì dùng Postgres.
  - Không có thì dùng file trong thư mục dữ liệu như trước.

Cách này giúp test và môi trường local chạy không cần database, còn trên
Render chỉ cần đặt biến môi trường là dữ liệu sống qua các lần deploy.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from data_storage import backup_critical_file, data_file, write_json_atomic

DATABASE_URL = os.environ.get("STUDYSYNC_DATABASE_URL", "").strip()

DOCUMENT_LOCK = threading.RLock()
_POOL: Any = None
_POOL_LOCK = threading.Lock()
_DB_LOCK = threading.RLock()

# Neon tu tat computer khi khong co request (scale to zero sau 5 phut).
# Lan mo dau tien sau khi tinh la co the cham 2-5 giay, vuot qua thoi gian cho
# phep cua Render nen nguoi dung thay du dung mat khau cung bi tu choi.
# Giu mot ban trong bo nho de phan lon cac lan doc deu ra duoc ngay.
USERS_CACHE_TTL_SECONDS = 60.0
_USERS_CACHE: dict[str, Any] = {"value": None, "expires": 0.0}

# Tên biến trong module dịch vụ giữ đường dẫn file tĩnh.
# Khi test monkeypatch các biến này, dữ liệu sẽ ghi vào thư mục tạm.
_OVERRIDE_ATTRS = {
    "users": ("auth_service", "USERS_FILE"),
    "link_requests": ("auth_service", "LINK_REQUESTS_FILE"),
    "feedback_inbox": ("feedback_service", "INBOX_FILE"),
    "feature_usage": ("owner_service", "USAGE_FILE"),
    "push_reminder_state": ("backend.notification_service", "PUSH_REMINDER_STATE_FILE"),
    "push_schedule_state": ("backend.notification_service", "PUSH_SCHEDULE_STATE_FILE"),
    "mobile_push_subscriptions": ("backend.notification_service", "MOBILE_PUSH_SUBSCRIPTIONS_FILE"),
    "reminder_preferences": ("backend.notification_service", "REMINDER_PREFERENCES_FILE"),
    "push_status": ("backend.notification_service", "PUSH_STATUS_FILE"),
    "web_push_subscriptions": ("backend.notification_service", "WEB_PUSH_SUBSCRIPTIONS_FILE"),
}


def is_postgres() -> bool:
    return bool(DATABASE_URL)


def _init_pool() -> Any:
    global _POOL
    if _POOL is not None:
        return _POOL
    with _POOL_LOCK:
        if _POOL is None:
            from psycopg_pool import ConnectionPool

            from psycopg.rows import dict_row

            _POOL = ConnectionPool(
                DATABASE_URL,
                min_size=1,
                max_size=5,
                kwargs={"row_factory": dict_row},
                timeout=10.0,
                max_idle=300.0,
                open=True,
            )
            with _POOL.connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS studysync_documents (
                        key TEXT PRIMARY KEY,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                conn.commit()
    return _POOL


def _document_path(key: str) -> Path:
    target = _OVERRIDE_ATTRS.get(key)
    if target is not None:
        module_name, attr = target
        module = sys.modules.get(module_name)
        value = getattr(module, attr, None) if module is not None else None
        if value:
            return Path(value)
    return data_file(f"{key}.json")


def _postgres_load(key: str) -> Any:
    pool = _init_pool()
    with _DB_LOCK, pool.connection() as conn:
        row = conn.execute(
            "SELECT payload FROM studysync_documents WHERE key=%s", (key,)
        ).fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get("payload")
    return row[0]

def _postgres_save(key: str, value: Any) -> None:
    pool = _init_pool()
    with _DB_LOCK, pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO studysync_documents (key, payload, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key) DO UPDATE
            SET payload = EXCLUDED.payload, updated_at = now()
            """,
            (key, json.dumps(value, ensure_ascii=False)),
        )
        conn.commit()


def clear_cache(key: str | None = None) -> None:
    """Xoa cache trong bo nho (dung ngay sau khi ghi du lieu)."""
    with DOCUMENT_LOCK:
        if key is None or key == "users":
            _USERS_CACHE["value"] = None
            _USERS_CACHE["expires"] = 0.0


def _cache_read(key: str) -> tuple[bool, Any]:
    if key != "users" or not is_postgres():
        return False, None
    now = time.monotonic()
    if _USERS_CACHE["value"] is not None and _USERS_CACHE["expires"] > now:
        return True, _USERS_CACHE["value"]
    return False, None


def _cache_write(key: str, value: Any) -> None:
    if key != "users" or not is_postgres():
        return
    _USERS_CACHE["value"] = value
    _USERS_CACHE["expires"] = time.monotonic() + USERS_CACHE_TTL_SECONDS


def load_document(key: str, default: Any, label: str | None = None) -> Any:
    """Đọc một tài liệu. Trả về `default` nếu chưa có dữ liệu."""
    name = label or key
    with DOCUMENT_LOCK:
        hit, cached = _cache_read(key)
        if hit:
            return cached
        if is_postgres():
            value = _postgres_load(key)
            result = default if value is None else value
            _cache_write(key, result)
            return result
        path = _document_path(key)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Không đọc được dữ liệu {name} tại {path}.") from exc


def save_document(key: str, value: Any) -> None:
    """Ghi một tài liệu, giữ bản sao lưu trước khi ghi đè."""
    with DOCUMENT_LOCK:
        if is_postgres():
            _postgres_save(key, value)
            # Nap lai bang gia tri vua ghi, khong xoa cache: xoa o day se lam
            # lan doc sau day quay ve database va cham.
            _cache_write(key, value)
            return
        backup_critical_file(f"{key}.json")
        write_json_atomic(_document_path(key), value)


def storage_status() -> dict[str, Any]:
    return {
        "backend": "postgres" if is_postgres() else "file",
        "database_configured": is_postgres(),
    }

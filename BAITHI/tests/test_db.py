"""Kiểm tra lớp lưu trữ: file JSON và Postgres.

Các test Postgres dùng đối tượng giả cho connection pool, nhờ vậy chạy được
offline mà vẫn kiểm tra đúng câu SQL và tham số gửi đi.
"""
import json
import sys

import db
import data_storage
from database.study_repository import StudyRepository


def test_uses_file_backend_without_database_url(monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    assert db.is_postgres() is False
    assert db.storage_status()["backend"] == "file"


def test_uses_postgres_backend_with_database_url(monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@host/db")
    assert db.is_postgres() is True
    assert db.storage_status()["backend"] == "postgres"


def _isolate_file_backend(tmp_path, monkeypatch):
    """Tách test khoi du lieu that.

    Quan trong: _document_path uu tien bien giu duong dan cua module dich vu
    (auth_service.USERS_FILE...), nen phai tro chung sang file trong tmp.
    Neu khong, test se ghi de len du lieu tai khoan that.
    """
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(data_storage, "DATA_DIR", tmp_path / "persistent")
    monkeypatch.setattr(data_storage, "LEGACY_DATA_DIR", tmp_path / "legacy")
    (tmp_path / "legacy").mkdir(parents=True, exist_ok=True)
    (tmp_path / "persistent").mkdir(parents=True, exist_ok=True)
    for key, (module_name, attr) in db._OVERRIDE_ATTRS.items():
        module = sys.modules.get(module_name)
        if module is not None:
            monkeypatch.setattr(module, attr, tmp_path / "persistent" / f"{key}.json")
    return tmp_path / "persistent"


def test_file_backend_round_trip(tmp_path, monkeypatch):
    data_dir = _isolate_file_backend(tmp_path, monkeypatch)

    db.save_document("users", {"users": [{"username": "hs01"}]})
    loaded = db.load_document("users", {"users": []})

    assert loaded["users"][0]["username"] == "hs01"
    assert (data_dir / "users.json").is_file()


def test_file_backend_returns_default_when_missing(tmp_path, monkeypatch):
    _isolate_file_backend(tmp_path, monkeypatch)

    assert db.load_document("users", {"users": []}) == {"users": []}


def test_file_backend_reports_corrupted_document(tmp_path, monkeypatch):
    data_dir = _isolate_file_backend(tmp_path, monkeypatch)
    (data_dir / "users.json").write_text('{"users": [', encoding="utf-8")

    import pytest

    with pytest.raises(RuntimeError, match="Không đọc được dữ liệu"):
        db.load_document("users", {"users": []}, "tài khoản")


class FakeCursor:
    def __init__(self, rows, description=None):
        self._rows = rows
        # psycopg tra ve None khi lenh khong tra ve hang (INSERT/UPDATE/DELETE).
        self.description = description if description is not None else [("col",)]

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    @property
    def rowcount(self):
        return len(self._rows)


class FakeConnection:
    def __init__(self, log, rows):
        self._log = log
        self._rows = rows
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        self._log.append((statement, params))
        return FakeCursor(self._rows)

    def commit(self):
        self.committed = True


class FakePool:
    def __init__(self, log, rows):
        self._log = log
        self._rows = rows
        self.closed = False

    def connection(self):
        return FakeConnection(self._log, self._rows)

    def close(self):
        self.closed = True


def test_postgres_backend_uses_documents_table(monkeypatch):
    log = []
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@host/db")
    monkeypatch.setattr(db, "_POOL", FakePool(log, [{"payload": {"users": []}}]))

    db.save_document("users", {"users": [{"username": "hs01"}]})

    assert any("INSERT INTO studysync_documents" in item[0] for item in log)
    saved = [item for item in log if "INSERT INTO studysync_documents" in item[0]][0]
    assert json.loads(saved[1][1])["users"][0]["username"] == "hs01"


def test_postgres_backend_loads_payload(monkeypatch):
    log = []
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@host/db")
    monkeypatch.setattr(
        db, "_POOL", FakePool(log, [{"payload": {"users": [{"username": "hs02"}]}}])
    )

    loaded = db.load_document("users", {"users": []})

    assert loaded["users"][0]["username"] == "hs02"
    assert any("SELECT payload" in item[0] for item in log)


def test_postgres_backend_upserts_with_on_conflict(monkeypatch, tmp_path):
    log = []
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@host/db")
    monkeypatch.setattr(db, "_POOL", FakePool(log, []))
    repository = StudyRepository(
        file_path=tmp_path / "study_data.json",
        db_path=tmp_path / "studysync.db",
    )

    repository.upsert_schedule_slot("morning", "2", 1, "Toán", "Cô An", "hs01")

    inserts = [item for item in log if "INSERT INTO schedule" in item[0]]
    assert inserts, "phai co cau lenh insert bang tham so khac dau %s"
    assert "ON CONFLICT (id) DO UPDATE" in inserts[0][0]
    assert "%s" in inserts[0][0]
    assert "hs01" in inserts[0][1]


def test_postgres_backend_reads_schedule_as_dicts(monkeypatch, tmp_path):
    log = []
    row = {
        "id": "lesson-1", "owner_username": "hs01", "session": "morning",
        "day": "2", "period": 1, "subject": "Toán", "lecturer": "Cô An",
        "reminder_minutes": 30, "start": "", "room": "",
    }
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@host/db")
    monkeypatch.setattr(db, "_POOL", FakePool(log, [row]))
    repository = StudyRepository(
        file_path=tmp_path / "study_data.json",
        db_path=tmp_path / "studysync.db",
    )

    schedule = repository.get_schedule("hs01")

    assert schedule[0]["subject"] == "Toán"
    assert isinstance(schedule[0], dict)
    selects = [item for item in log if "SELECT * FROM schedule" in item[0]]
    assert "%s" not in selects[0][0].split("WHERE")[0]


def test_account_data_status_reads_postgres(monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@host/db")
    monkeypatch.setattr(db, "_POOL", FakePool([], [{"payload": {"users": [{"username": "a"}, {"username": "b"}]}}]))
    monkeypatch.setenv("STUDYSYNC_SESSION_SECRET", "k" * 40)

    status = data_storage.account_data_status()

    assert status["backend"] == "postgres"
    assert status["user_count"] == 2
    assert status["has_session_secret"] is True

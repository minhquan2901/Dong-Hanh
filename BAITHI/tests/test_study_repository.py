import sqlite3

from database.study_repository import StudyRepository


def test_upsert_schedule_slot_updates_existing_lesson(tmp_path):
    repository = StudyRepository(
        file_path=tmp_path / "study_data.json",
        db_path=tmp_path / "studysync.sqlite3",
    )

    created = repository.upsert_schedule_slot("morning", "2", 1, "Toán", "Cô An", "student01")
    updated = repository.upsert_schedule_slot("morning", "2", 1, "Ngữ văn", "Thầy Bình", "student01")

    assert updated["id"] == created["id"]
    assert updated["subject"] == "Ngữ văn"
    assert updated["lecturer"] == "Thầy Bình"
    assert repository.get_schedule("student01") == [updated]
    assert repository.get_schedule("student02") == []


def test_upsert_schedule_slots_adds_multiple_lessons_in_one_call(tmp_path):
    repository = StudyRepository(
        file_path=tmp_path / "study_data.json",
        db_path=tmp_path / "studysync.sqlite3",
    )

    created = repository.upsert_schedule_slots([
        {"session": "morning", "day": "2", "period": 1, "subject": "Toán", "lecturer": "Cô An", "username": "student01"},
        {"session": "morning", "day": "2", "period": 2, "subject": "Lý", "lecturer": "Thầy Bình", "username": "student01"},
    ])

    assert len(created) == 2
    assert [item["subject"] for item in repository.get_schedule("student01")] == ["Toán", "Lý"]
    assert repository.get_schedule("student02") == []


def test_schedule_and_assignments_are_isolated_per_student(tmp_path):
    repository = StudyRepository(
        file_path=tmp_path / "study_data.json",
        db_path=tmp_path / "studysync.sqlite3",
    )
    repository.upsert_schedule_slot("morning", "2", 1, "Toán A", "Cô An", "student-a")
    repository.upsert_schedule_slot("morning", "2", 1, "Văn B", "Thầy Bình", "student-b")
    repository.upsert_schedule_slot("morning", "2", 2, "Lý A", "Cô An", "student-a")
    assignment_a = repository.add_assignment("Bài A", "Toán", "2026-10-01", "Cao", "student-a")
    assignment_b = repository.add_assignment("Bài B", "Văn", "2026-10-02", "Thấp", "student-b")

    assert [item["subject"] for item in repository.get_schedule("student-a")] == ["Toán A", "Lý A"]
    assert [item["subject"] for item in repository.get_schedule("student-b")] == ["Văn B"]
    assert [item["title"] for item in repository.get_assignments("student-a")] == ["Bài A"]
    assert [item["title"] for item in repository.get_assignments("student-b")] == ["Bài B"]
    assert not repository.set_assignment_completed(assignment_a["id"], True, "student-b")
    assert not repository.delete_assignment(assignment_a["id"], "student-b")
    assert not repository.delete_schedule_slot("morning", "2", 2, "student-b")
    assert len(repository.get_schedule("student-a")) == 2


def test_existing_database_schema_migrates_records_without_exposing_them(tmp_path, monkeypatch):
    db_path = tmp_path / "existing.sqlite3"
    file_path = tmp_path / "study_data.json"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE schedule (id TEXT PRIMARY KEY, session TEXT, day TEXT, period INTEGER, subject TEXT, lecturer TEXT, reminder_minutes INTEGER DEFAULT 30, start TEXT DEFAULT '', room TEXT DEFAULT '')")
        conn.execute("CREATE TABLE assignments (id TEXT PRIMARY KEY, title TEXT, subject TEXT, due_date TEXT, priority TEXT, completed INTEGER DEFAULT 0)")
        conn.execute("INSERT INTO schedule (id, session, day, period, subject, lecturer) VALUES ('old-slot', 'morning', '2', 1, 'Lịch cũ', 'GV')")
        conn.execute("INSERT INTO assignments (id, title, subject, due_date, priority, completed) VALUES ('old-task', 'Bài cũ', 'Toán', '2026-10-01', 'Cao', 0)")

    monkeypatch.delenv("LEGACY_STUDY_OWNER_USERNAME", raising=False)
    repository = StudyRepository(file_path=file_path, db_path=db_path)

    assert repository.get_schedule("student-a") == []
    assert repository.get_assignments("student-a") == []
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM schedule").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] == 1


def test_legacy_database_rows_can_be_mapped_to_explicit_owner(tmp_path, monkeypatch):
    db_path = tmp_path / "existing.sqlite3"
    file_path = tmp_path / "study_data.json"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE schedule (id TEXT PRIMARY KEY, session TEXT, day TEXT, period INTEGER, subject TEXT, lecturer TEXT, reminder_minutes INTEGER DEFAULT 30, start TEXT DEFAULT '', room TEXT DEFAULT '')")
        conn.execute("CREATE TABLE assignments (id TEXT PRIMARY KEY, title TEXT, subject TEXT, due_date TEXT, priority TEXT, completed INTEGER DEFAULT 0)")
        conn.execute("INSERT INTO schedule (id, session, day, period, subject, lecturer) VALUES ('old-slot', 'morning', '2', 1, 'Lịch cũ', 'GV')")
        conn.execute("INSERT INTO assignments (id, title, subject, due_date, priority, completed) VALUES ('old-task', 'Bài cũ', 'Toán', '2026-10-01', 'Cao', 0)")

    monkeypatch.setenv("LEGACY_STUDY_OWNER_USERNAME", "student-a")
    repository = StudyRepository(file_path=file_path, db_path=db_path)

    assert [item["subject"] for item in repository.get_schedule("student-a")] == ["Lịch cũ"]
    assert [item["title"] for item in repository.get_assignments("student-a")] == ["Bài cũ"]
    assert repository.get_schedule("student-b") == []
    assert repository.get_assignments("student-b") == []

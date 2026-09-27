from database.study_repository import StudyRepository


def test_upsert_schedule_slot_updates_existing_lesson(tmp_path):
    repository = StudyRepository(
        file_path=tmp_path / "study_data.json",
        db_path=tmp_path / "studysync.sqlite3",
    )

    created = repository.upsert_schedule_slot("morning", "2", 1, "Toán", "Cô An")
    updated = repository.upsert_schedule_slot("morning", "2", 1, "Ngữ văn", "Thầy Bình")

    assert updated["id"] == created["id"]
    assert updated["subject"] == "Ngữ văn"
    assert updated["lecturer"] == "Thầy Bình"
    assert repository.get_schedule() == [updated]


def test_upsert_schedule_slots_adds_multiple_lessons_in_one_call(tmp_path):
    repository = StudyRepository(
        file_path=tmp_path / "study_data.json",
        db_path=tmp_path / "studysync.sqlite3",
    )

    created = repository.upsert_schedule_slots([
        {"session": "morning", "day": "2", "period": 1, "subject": "Toán", "lecturer": "Cô An"},
        {"session": "morning", "day": "2", "period": 2, "subject": "Lý", "lecturer": "Thầy Bình"},
    ])

    assert len(created) == 2
    assert [item["subject"] for item in repository.get_schedule()] == ["Toán", "Lý"]

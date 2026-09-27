import json

import data_storage


def test_data_file_migrates_legacy_once_without_overwriting_persistent_data(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "legacy"
    persistent_dir = tmp_path / "persistent"
    legacy_dir.mkdir()
    legacy_file = legacy_dir / "users.json"
    legacy_file.write_text('{"users": [{"username": "legacy"}]}', encoding="utf-8")
    monkeypatch.setattr(data_storage, "LEGACY_DATA_DIR", legacy_dir)
    monkeypatch.setattr(data_storage, "DATA_DIR", persistent_dir)

    persistent_file = data_storage.data_file("users.json")

    assert json.loads(persistent_file.read_text(encoding="utf-8"))["users"][0]["username"] == "legacy"
    data_storage.write_json_atomic(persistent_file, {"users": [{"username": "new"}]})
    assert data_storage.data_file("users.json") == persistent_file
    assert json.loads(persistent_file.read_text(encoding="utf-8"))["users"][0]["username"] == "new"


def test_write_json_atomic_creates_parent_and_valid_json(tmp_path):
    target = tmp_path / "persistent" / "nested" / "users.json"

    data_storage.write_json_atomic(target, {"users": [{"username": "student01"}]})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "users": [{"username": "student01"}],
    }
    assert list(target.parent.glob("*.tmp")) == []
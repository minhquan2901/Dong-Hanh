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


def test_backup_critical_file_keeps_copy_before_overwrite(tmp_path, monkeypatch):
    data_dir = tmp_path / "persistent"
    data_dir.mkdir()
    monkeypatch.setattr(data_storage, "DATA_DIR", data_dir)
    (data_dir / "users.json").write_text('{"users": [{"username": "student01"}]}', encoding="utf-8")

    saved = data_storage.backup_critical_file("users.json")

    assert saved is not None
    assert json.loads(saved.read_text(encoding="utf-8"))["users"][0]["username"] == "student01"


def test_backup_skips_missing_and_corrupted_files(tmp_path, monkeypatch):
    data_dir = tmp_path / "persistent"
    data_dir.mkdir()
    monkeypatch.setattr(data_storage, "DATA_DIR", data_dir)

    assert data_storage.backup_critical_file("users.json") is None

    (data_dir / "users.json").write_text("{khong phai json", encoding="utf-8")
    assert data_storage.backup_critical_file("users.json") is None
    assert data_storage.list_backups("users.json") == []


def test_restore_latest_backup_recovers_accounts(tmp_path, monkeypatch):
    data_dir = tmp_path / "persistent"
    data_dir.mkdir()
    monkeypatch.setattr(data_storage, "DATA_DIR", data_dir)
    (data_dir / "users.json").write_text('{"users": [{"username": "student01"}]}', encoding="utf-8")
    data_storage.backup_critical_file("users.json")

    (data_dir / "users.json").write_text('{"users": []}', encoding="utf-8")
    restored = data_storage.restore_latest_backup("users.json")

    assert restored is not None
    assert json.loads((data_dir / "users.json").read_text(encoding="utf-8"))["users"][0]["username"] == "student01"


def test_restore_ignores_corrupted_backup(tmp_path, monkeypatch):
    data_dir = tmp_path / "persistent"
    data_dir.mkdir()
    monkeypatch.setattr(data_storage, "DATA_DIR", data_dir)
    backups = data_dir / "backups"
    backups.mkdir()
    (backups / "users.json.20990101-000000.bak.json").write_text("{hong", encoding="utf-8")

    assert data_storage.restore_latest_backup("users.json") is None


def test_account_data_status_reports_users_and_secret(tmp_path, monkeypatch):
    data_dir = tmp_path / "persistent"
    data_dir.mkdir()
    monkeypatch.setattr(data_storage, "DATA_DIR", data_dir)
    (data_dir / "users.json").write_text('{"users": [{"username": "a"}, {"username": "b"}]}', encoding="utf-8")
    (data_dir / "session_signing_secret.json").write_text(json.dumps("k" * 40), encoding="utf-8")

    status = data_storage.account_data_status()

    assert status["user_count"] == 2
    assert status["has_session_secret"] is True
    assert status["files"]["users.json"]["exists"] is True


def test_prune_backups_keeps_configured_limit(tmp_path, monkeypatch):
    data_dir = tmp_path / "persistent"
    data_dir.mkdir()
    monkeypatch.setattr(data_storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(data_storage, "BACKUP_KEEP", 2)
    (data_dir / "users.json").write_text('{"users": []}', encoding="utf-8")

    for stamp in ("20240101-000001", "20240101-000002", "20240101-000003"):
        backups = data_dir / "backups"
        backups.mkdir(exist_ok=True)
        (backups / f"users.json.{stamp}.bak.json").write_text('{"users": []}', encoding="utf-8")
    data_storage.backup_critical_file("users.json")

    backups = data_storage.list_backups("users.json")
    assert len(backups) <= 3
    assert data_storage._prune_backups(data_dir / "backups", 2) is None
    assert len(data_storage.list_backups("users.json")) == 2
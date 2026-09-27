from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
LEGACY_DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR = Path(os.environ.get("STUDYSYNC_DATA_DIR", LEGACY_DATA_DIR)).expanduser()

# Cac file duoc bao ve: mat file nay se mat tai khoan nguoi dung.
CRITICAL_FILES = (
    "users.json",
    "link_requests.json",
    "session_signing_secret.json",
)

# Giu ban sao luu gan nhat de khoi phuc khi bi ghi de rong.
BACKUP_DIRNAME = "backups"
BACKUP_KEEP = int(os.environ.get("STUDYSYNC_BACKUP_KEEP", "20"))
_BACKUP_SUFFIX = ".bak.json"


def data_file(filename: str) -> Path:
    target = DATA_DIR / filename
    legacy = LEGACY_DATA_DIR / filename
    if target.resolve() == legacy.resolve() or target.exists() or not legacy.is_file():
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        shutil.copy2(legacy, temporary_path)
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return target


def write_json_atomic(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(value, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def backup_dir() -> Path:
    return DATA_DIR / BACKUP_DIRNAME


def _validate_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Khong doc duoc du lieu tai {path}.") from exc


def _prune_backups(directory: Path, keep: int) -> None:
    if keep <= 0:
        return
    backups = sorted(directory.glob("*" + _BACKUP_SUFFIX), key=lambda item: item.name, reverse=True)
    for stale in backups[keep:]:
        stale.unlink(missing_ok=True)


def backup_critical_file(filename: str) -> Path | None:
    """Giu ban sao file quan trong truoc khi no bi ghi de."""
    source = DATA_DIR / filename
    if not source.is_file():
        return None
    try:
        _validate_json(source)
    except RuntimeError:
        return None
    directory = backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    destination = directory / f"{filename}.{stamp}{_BACKUP_SUFFIX}"
    counter = 1
    while destination.exists():
        destination = directory / f"{filename}.{stamp}-{counter}{_BACKUP_SUFFIX}"
        counter += 1
    shutil.copy2(source, destination)
    _prune_backups(directory, BACKUP_KEEP)
    return destination


def list_backups(filename: str) -> list[Path]:
    directory = backup_dir()
    if not directory.is_dir():
        return []
    return sorted(
        (item for item in directory.glob(f"{filename}.*{_BACKUP_SUFFIX}") if item.is_file()),
        key=lambda item: item.name,
        reverse=True,
    )


def restore_latest_backup(filename: str) -> Path | None:
    """Khoi phuc ban sao luu moi nhat cua mot file quan trong."""
    for candidate in list_backups(filename):
        try:
            _validate_json(candidate)
        except RuntimeError:
            continue
        target = DATA_DIR / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, target)
        return target
    return None


def account_data_status() -> dict[str, Any]:
    """Bao cao tinh trang du lieu tai khoan de theo doi sau moi lan deploy."""
    report: dict[str, Any] = {
        "data_dir": str(DATA_DIR),
        "using_persistent_dir": is_using_persistent_dir(),
        "files": {},
        "user_count": 0,
        "has_session_secret": False,
    }
    for filename in CRITICAL_FILES:
        path = DATA_DIR / filename
        entry: dict[str, Any] = {"exists": path.is_file(), "backups": len(list_backups(filename))}
        if path.is_file():
            try:
                payload = _validate_json(path)
            except RuntimeError as exc:
                entry["error"] = str(exc)
            else:
                if filename == "users.json" and isinstance(payload, dict):
                    users = payload.get("users")
                    entry["users"] = len(users) if isinstance(users, list) else 0
                if filename == "session_signing_secret.json":
                    entry["valid_secret"] = isinstance(payload, str) and len(payload) >= 32
        report["files"][filename] = entry
    users_entry = report["files"].get("users.json", {})
    report["user_count"] = users_entry.get("users", 0)
    report["has_session_secret"] = bool(report["files"].get("session_signing_secret.json", {}).get("valid_secret"))
    return report


def is_using_persistent_dir() -> bool:
    return DATA_DIR.resolve() != LEGACY_DATA_DIR.resolve()
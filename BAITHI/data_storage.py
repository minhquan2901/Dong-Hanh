from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
LEGACY_DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR = Path(os.environ.get("STUDYSYNC_DATA_DIR", LEGACY_DATA_DIR)).expanduser()


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
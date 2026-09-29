"""Dedicated reminder process: python reminder_worker.py.

Khoa o cap du lieu chung (Postgres advisory lock hoac SQLite file lock) de
nhieu instance cua Render khong gui trung cung mot moc nhac.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path

from backend.notification_service import run_reminder_tick, send_schedule_reminders
from data_storage import data_file
from db import _init_pool, is_postgres

logger = logging.getLogger(__name__)

# Postgres advisory lock id. Giu nguyen de worker va cron khong gui trung nhac.
LOCK_ID = 735_194_022


@contextmanager
def reminder_lock():
    """Khoa khong cho chan, giu xuyen suat gui thong bao."""
    if is_postgres():
        with _init_pool().connection() as conn:
            acquired = conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]
            if not acquired:
                yield False
                return
            try:
                yield True
            finally:
                conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
                conn.commit()
        return
    # SQLite file lock works across processes on local filesystem (unlike threading.Lock).
    import sqlite3
    lock_path = data_file("reminder_worker_lock.sqlite3")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(lock_path, timeout=0.1, isolation_level=None) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            yield False
            return
        try:
            yield True
        finally:
            conn.rollback()


def tick() -> dict:
    """Mot nhip nhac: tra ve ket qua, kem `skipped` khi worker khac giu khoa."""
    with reminder_lock() as acquired:
        if not acquired:
            logger.info("Bo qua nhip nhac: worker khac dang giu khoa")
            return {"skipped": "locked", "reminders": [], "schedule": []}
        result = {"reminders": run_reminder_tick(), "schedule": send_schedule_reminders()}
        logger.info(
            "Nhip nhac: %d han bai, %d tiet hoc",
            len(result["reminders"]),
            len(result["schedule"]),
        )
        return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    interval = max(30, int(os.getenv("REMINDER_TICK_SECONDS", "60")))
    logger.info("Worker nhac bat dau, chay moi %d giay", interval)
    while True:
        try:
            tick()
        except Exception:  # worker khong duoc chet vi mot lan gui that bai
            logger.exception("Nhip nhac that bai")
        time.sleep(interval)


if __name__ == "__main__":
    main()

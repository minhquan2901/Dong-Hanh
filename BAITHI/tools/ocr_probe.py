"""Kiểm chứng pipeline đọc ảnh thời khóa biểu trên ảnh mô phỏng."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.schedule_ocr import extract_timetable_slots

image = Path(__file__).with_name("sample_timetable.png").read_bytes()
slots, warnings = extract_timetable_slots(image)

grid: dict[tuple[str, str, int], str] = {}
for slot in slots:
    grid[(slot["session"], slot["day"], slot["period"])] = f"{slot['subject']} / {slot['lecturer']}"

print(f"Tong so tiet doc duoc: {len(slots)}")
for note in warnings:
    print(f"Canh bao: {note}")
for session in ("morning", "afternoon"):
    print(f"\n== {session} ==")
    for period in range(1, 7):
        row = [grid.get((session, day, period), "").ljust(30) for day in "234567"]
        if any(row):
            print(f"Tiet {period}: " + " | ".join(row))

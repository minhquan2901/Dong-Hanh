from __future__ import annotations

import os
import secrets
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, UploadFile

from backend.schedule_ocr import (
    MAX_TIMETABLE_IMAGE_BYTES,
    TimetableImageError,
    extract_timetable_slots,
)

app = FastAPI(title="StudySync OCR Service")
OCR_SERVICE_SECRET = os.getenv("OCR_SERVICE_SECRET", "").strip()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "StudySync OCR"}


@app.post("/ocr/timetable")
async def ocr_timetable(
    file: UploadFile = File(...),
    x_ocr_secret: str | None = Header(default=None, alias="X-OCR-Secret"),
) -> dict[str, Any]:
    if not OCR_SERVICE_SECRET or not x_ocr_secret or not secrets.compare_digest(x_ocr_secret, OCR_SERVICE_SECRET):
        raise HTTPException(status_code=403, detail="Không được phép gọi dịch vụ OCR.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Ảnh rỗng.")
    if len(raw) > MAX_TIMETABLE_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Ảnh vượt quá dung lượng cho phép.")
    try:
        slots, warnings = extract_timetable_slots(raw)
    except TimetableImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"slots": slots, "warnings": warnings}

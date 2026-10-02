from __future__ import annotations

import base64
import json
import os
import re
from typing import Any

import requests

from database.study_repository import MAX_PERIOD


MAX_TIMETABLE_IMAGE_BYTES = 8 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MODEL_NAME = re.compile(r"^[a-zA-Z0-9._-]+$")
_DAY_NAMES = {
    "2": ("thứ 2", "thứ hai"),
    "3": ("thứ 3", "thứ ba"),
    "4": ("thứ 4", "thứ tư"),
    "5": ("thứ 5", "thứ năm"),
    "6": ("thứ 6", "thứ sáu"),
    "7": ("thứ 7", "thứ bảy"),
}


class TimetableAIError(ValueError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def timetable_ai_available() -> bool:
    return bool(os.getenv("TIMETABLE_GEMINI_API_KEY", "").strip())


def _response_schema() -> dict[str, Any]:
    return {
        "type": "OBJECT",
        "properties": {
            "slots": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "session": {"type": "STRING", "enum": ["morning", "afternoon"]},
                        "day": {"type": "STRING", "enum": ["2", "3", "4", "5", "6", "7"]},
                        "period": {"type": "INTEGER", "minimum": 1, "maximum": MAX_PERIOD},
                        "subject": {"type": "STRING"},
                        "lecturer": {"type": "STRING"},
                    },
                    "required": ["session", "day", "period", "subject", "lecturer"],
                },
            },
            "warnings": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["slots", "warnings"],
    }


def _normalize_result(payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("slots"), list):
        raise TimetableAIError("AI không trả về bảng thời khóa biểu hợp lệ.")

    day_aliases = {
        alias: day
        for day, aliases in _DAY_NAMES.items()
        for alias in (day, *aliases)
    }
    slots: list[dict[str, Any]] = []
    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = ["AI trả về cảnh báo không đúng định dạng."]
    normalized_warnings = [str(item).strip()[:240] for item in warnings if str(item).strip()]
    seen_slots: set[tuple[str, str, int]] = set()

    for item in payload["slots"]:
        if not isinstance(item, dict):
            raise TimetableAIError("Một tiết học AI trả về không đúng định dạng.")

        session = str(item.get("session", "")).strip().lower()
        day_text = str(item.get("day", "")).strip().lower()
        day = day_aliases.get(day_text)
        try:
            period = int(item.get("period"))
        except (TypeError, ValueError):
            period = 0
        subject = str(item.get("subject", "")).strip()[:60]
        lecturer = str(item.get("lecturer", "")).strip()[:40]

        if session not in {"morning", "afternoon"} or day is None:
            raise TimetableAIError("AI trả về buổi hoặc thứ không hợp lệ.")
        if not 1 <= period <= MAX_PERIOD or not subject:
            raise TimetableAIError("AI trả về tiết hoặc tên môn không hợp lệ.")

        key = (session, day, period)
        if key in seen_slots:
            normalized_warnings.append(f"AI nhận diện trùng tiết {period}, thứ {day}; đã bỏ bản trùng.")
            continue
        seen_slots.add(key)
        slots.append({
            "session": session,
            "day": day,
            "period": period,
            "subject": subject,
            "lecturer": lecturer,
        })

    if not slots:
        raise TimetableAIError("Không nhận ra tiết học nào trong ảnh.", 422)
    slots.sort(key=lambda item: (item["session"], item["day"], item["period"]))
    return slots, normalized_warnings


def extract_timetable_slots_from_image(image_bytes: bytes, mime_type: str) -> tuple[list[dict[str, Any]], list[str]]:
    api_key = os.getenv("TIMETABLE_GEMINI_API_KEY", "").strip()
    if not api_key:
        raise TimetableAIError("Chưa cấu hình TIMETABLE_GEMINI_API_KEY.", 503)
    if mime_type not in SUPPORTED_IMAGE_TYPES:
        raise TimetableAIError("Chỉ hỗ trợ ảnh JPG, PNG hoặc WebP.", 415)

    model = os.getenv("TIMETABLE_GEMINI_MODEL", "gemini-3.8-flash").strip()
    if not _MODEL_NAME.fullmatch(model):
        raise TimetableAIError("Tên model Gemini không hợp lệ.", 503)

    prompt = (
        "Đọc ảnh thời khóa biểu trường học và chỉ trả về dữ liệu trong JSON schema. "
        "Không tự suy đoán môn, giáo viên hoặc tiết bị mờ; nếu không chắc, bỏ tiết đó "
        "và nêu lý do ngắn gọn trong warnings. Tách bảng theo buổi sáng/chiều. "
        "day dùng chuỗi 2 đến 7; session chỉ là morning hoặc afternoon. "
        "period là thứ tự hàng tiết từ trên xuống trong đúng buổi; hàng trống vẫn "
        "tính vào thứ tự, không dồn các tiết bên dưới lên. Tách lecturer khỏi subject "
        "nếu ô có dạng 'môn - giáo viên'. Trả môn và giáo viên bằng tiếng Việt như ảnh."
    )
    request_body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": base64.b64encode(image_bytes).decode("ascii"),
                    }
                },
            ]
        }],
        "generationConfig": {
            "temperature": 0,
            "candidateCount": 1,
            "maxOutputTokens": 4096,
            "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            "responseFormat": {
                "text": {
                    "mimeType": "APPLICATION_JSON",
                    "schema": _response_schema(),
                }
            },
        },
    }

    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key},
            json=request_body,
            timeout=(8, 50),
        )
    except requests.Timeout as exc:
        raise TimetableAIError("Gemini xử lý ảnh quá lâu. Hãy thử lại sau.", 504) from exc
    except requests.RequestException as exc:
        raise TimetableAIError("Không kết nối được Gemini để đọc ảnh.", 503) from exc

    if response.status_code == 429:
        raise TimetableAIError("Gemini đang giới hạn lượt gọi hoặc hết quota. Hãy thử lại sau.", 503)
    if response.status_code in {401, 403}:
        raise TimetableAIError("Gemini từ chối API key. Kiểm tra TIMETABLE_GEMINI_API_KEY.", 503)
    if response.status_code >= 400:
        raise TimetableAIError(f"Gemini không xử lý được ảnh (HTTP {response.status_code}).", 502)

    try:
        response_body = response.json()
        parts = response_body["candidates"][0]["content"]["parts"]
        model_text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        result = json.loads(model_text)
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise TimetableAIError("Gemini không trả về JSON thời khóa biểu hợp lệ.") from exc

    return _normalize_result(result)
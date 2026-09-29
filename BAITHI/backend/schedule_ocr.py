"""Doc anh thoi khoa bieu va suy ra cac tiet hoc.

Cach hoat dong:
  1. Chay OCR tren anh, lay toa do tung dong chu.
  2. Do tieu de cot (Thu 2 ... Thu 7) de biet moi cot ung voi thu may.
  3. Do nhan buoi (SANG / CHIEU) de tach bang tren va bang duoi.
  4. Trong moi bang, gom chu theo cot ngang va hang doc, ghep thanh noi dung
     o, roi tach theo dau `-` de lay mon hoc va giao vien.

May chay hoan toan offline, khong can API key.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import defaultdict
from typing import Any

# Nhan cot theo thu, da bo dau va bo khoang trang de so khop chinh xac.
# So khop dang khit tranh loi "thu bay" bi nhan nham thanh "thu ba".
DAY_KEYS: dict[str, tuple[str, ...]] = {
    "2": ("thuhai", "thu2", "t2"),
    "3": ("thuba", "thu3", "t3"),
    "4": ("thutu", "thu4", "t4"),
    "5": ("thunam", "thu5", "t5"),
    "6": ("thusau", "thu6", "t6"),
    "7": ("thubay", "chunhat", "thu7", "t7", "cn"),
}

SESSION_KEYS = {
    "morning": ("sang", "buoisang", "casang", "morning"),
    "afternoon": ("chieu", "buoichieu", "cachieu", "afternoon", "toi"),
}

# Từ khoá nhận diện nhãn buổi, dùng để dò trong câu đầy đủ.
SESSION_MARKERS = {
    "morning": ("buoisang", "casang", "sang"),
    "afternoon": ("buoichieu", "cachieu", "chieu", "toi"),
}

_DAY_KEY_SET = {name for keys in DAY_KEYS.values() for name in keys}

# Ảnh chụp từ điện thoại thường 2-5 MB, đặt trần 12 MB cho sẵn.
MAX_TIMETABLE_IMAGE_BYTES = 12 * 1024 * 1024

# Thời khóa biểu lưu được tiết 1 đến MAX_PERIOD, khớp với giới hạn ở
# database.study_repository. Trước đây để 5 nên bỏ mất tiết 6, 7 có thật.
from database.study_repository import MAX_PERIOD

MAX_PERIODS_PER_SESSION = MAX_PERIOD

SESSION_LABELS = {"morning": "Buổi sáng", "afternoon": "Buổi chiều"}

# Ky hieu mon viet tat hay gap, dung de chuan hoa ten hien thi.
SUBJECT_ALIASES: dict[str, str] = {
    "toan": "Toán", "ngu van": "Ngữ văn", "tv": "Ngữ văn",
    "tieng anh": "Tiếng Anh", "ta": "Tiếng Anh", "tieng phap": "Tiếng Pháp",
    "tieng trung": "Tiếng Trung", "tieng han": "Tiếng Hàn", "tieng nga": "Tiếng Nga",
    "tieng duc": "Tiếng Đức", "khtn": "KHTN", "lsdl": "LS&ĐL", "gdcd": "GDCD",
    "gde": "GDKT&PL", "gdktpl": "GDKT&PL", "vat li": "Vật lí", "hoa hoc": "Hóa học",
    "sinh hoc": "Sinh học", "lich su": "Lịch sử", "dia ly": "Địa lí",
    "tin hoc": "Tin học", "cong nghe": "Công nghệ", "gdtc": "GDTC",
    "am nhac": "Âm nhạc", "my thuat": "Mỹ thuật", "hdtnhn": "HĐTN-HN",
    "gdp": "GD địa phương", "chuyende": "Chuyên đề", "stem": "STEM",
}

_SPLIT_ON_DASH = re.compile(r"\s*[-\u2013\u2014]\s*")
_CLEAN = re.compile(r"[\u2022\u00b7|]+")

_ENGINE: Any = None


class TimetableImageError(ValueError):
    """Anh khong doc duoc thanh bang thoi khoa bieu."""


def _engine() -> Any:
    """Nap OCR mot lan roi dung lai, vi khoi tao model kha nang."""
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR

        _ENGINE = RapidOCR()
    return _ENGINE


def _strip_diacritics(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", str(text or ""))
        if not unicodedata.combining(char)
    )


def _normalize(text: str) -> str:
    """Bo dau, bo ky tu la va gop khoang trang de so khop on dinh."""
    cleaned = _strip_diacritics(_CLEAN.sub(" ", str(text or "")))
    return re.sub(r"[^a-z0-9]+", " ", cleaned.lower()).strip()


def _key(text: str) -> str:
    """Dang so khop khit, bo ca khoang trang ben trong."""
    return _normalize(text).replace(" ", "")


def _read_lines(image_bytes: bytes) -> tuple[list[dict[str, Any]], list[float]]:
    """Tra ve cac dong chu va cac duong nam ngang cua bang.

    Duong ke bi bo trong rat quan trong: mot tiet khong co mon nao se khong
    co dong chu nao, nhung so tiet van phai dung.
    """
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - phu thuoc cai san
        raise TimetableImageError(
            "Máy chủ thiếu thư viện đọc ảnh. Chạy: pip install -r requirements.txt"
        ) from exc

    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise TimetableImageError("Không đọc được tệp ảnh. Hãy thử lại với ảnh PNG hoặc JPG.")

    # Phong lon anh chup tu dien thoai, chu nho trong o se de nhan hon.
    height, width = image.shape[:2]
    if max(height, width) < 1800:
        image = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    grid_lines = _detect_grid_lines(image)

    result, _ = _engine()(image)
    if not result:
        raise TimetableImageError("Không tìm thấy chữ trong ảnh. Hãy chụp rõ, không mờ và không bị che.")

    lines: list[dict[str, Any]] = []
    for box, text, score in result:
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        clean = re.sub(r"\s+", " ", str(text or "")).strip()
        if not clean:
            continue
        lines.append({
            "text": clean,
            "score": float(score),
            "x1": min(xs), "x2": max(xs),
            "y1": min(ys), "y2": max(ys),
            "cx": (min(xs) + max(xs)) / 2,
            "cy": (min(ys) + max(ys)) / 2,
        })
    if not lines:
        raise TimetableImageError("Không tìm thấy chữ trong ảnh.")
    return lines, grid_lines


def _detect_grid_lines(image: Any) -> list[float]:
    """Tim cac duong ke ngang cua bang, tra ve toa do trung tam.

    Cach nay giu duoc so tiet khi mot hang rong hoan toan, truong hop OCR
    chi dua theo chu thi so tiet se bi lech.
    """
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

    # Moi dong anh co bao nhieu pixel den. Duong ke la dong ty le lon.
    # Typ ty le phai du "nhat" chu khong phai trung binh, vi chu trong o
    # lam dong ton tai mot phan chieu ngang.
    dark_per_row = (binary > 0).sum(axis=1) / max(1, binary.shape[1])
    candidates = np.where(dark_per_row > 0.30)[0]
    if candidates.size == 0:
        return []

    groups: list[list[int]] = [[int(candidates[0])]]
    for value in candidates[1:]:
        if value - groups[-1][-1] <= 3:
            groups[-1].append(int(value))
        else:
            groups.append([int(value)])

    merged: list[float] = []
    for group in groups:
        center = sum(group) / len(group)
        # Duong ke doi sat nhau phai gop lai, tranh dem thanh hai hang.
        if merged and center - merged[-1] < 8:
            continue
        merged.append(center)
    return merged


def _find_day_columns(lines: list[dict[str, Any]]) -> dict[str, float]:
    """Toa do giua cua tung cot, theo Thu 2 den Thu 7.

    Lay vi tri trung vi cua cac nhan khop de ben voi loi OCR lech mot chu.
    """
    centers: dict[str, list[float]] = defaultdict(list)
    for line in lines:
        key = _key(line["text"])
        for day, candidates in DAY_KEYS.items():
            if key in candidates:
                centers[day].append(line["cx"])
                break
    if len(centers) < 4:
        raise TimetableImageError(
            "Không nhận ra các cột thứ trong tuần. Hãy chụp trọn bảng, có đủ tiêu đề Thứ 2 đến Thứ 7."
        )
    return {day: sorted(values)[len(values) // 2] for day, values in centers.items()}


def _split_sessions(lines: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Chia dong chu theo bang sang va bang chieu.

    Neu khong thay nhan buoi nao, coi toan bo la buoi sang.
    """
    marks: list[tuple[float, str]] = []
    labels: list[int] = []
    for line in lines:
        key = _key(line["text"])
        if key in _DAY_KEY_SET:
            continue
        # Nhãn buổi trong TKB thật là câu đầy đủ, ví dụ
        # "Buổi sáng - Thứ 2 chào cờ từ 7h00-7h15", nên so theo từ khoá.
        if "buoi" not in key and "ca" not in key:
            continue
        for session, markers in SESSION_MARKERS.items():
            if any(marker in key for marker in markers):
                marks.append((line["cy"], session))
                labels.append(id(line))
                break
    if not marks:
        return {"morning": list(lines), "afternoon": []}

    marks.sort()
    result: dict[str, list[dict[str, Any]]] = {"morning": [], "afternoon": []}
    for index, (position, session) in enumerate(marks):
        # Chi lay dong nam duoi nhan buoi nay va tren nhan buoi ke tiep.
        upper = marks[index + 1][0] if index + 1 < len(marks) else float("inf")
        for line in lines:
            if id(line) in labels:
                continue
            if position < line["cy"] < upper:
                result[session].append(line)
    # Dong nam tren nhan buoi dau tien thuoc ve bang truoc do. Ảnh thực tế
    # thuong chi ghi "Buổi chiều" o bang duoi, nen phan tren phai la buổi sang.
    first_position, first_session = marks[0]
    if not any(session == "morning" for _, session in marks):
        for line in lines:
            if id(line) in labels or line["cy"] >= first_position:
                continue
            result["morning" if first_session == "afternoon" else "afternoon"].append(line)
    return result


def _assign_column(line: dict[str, Any], columns: dict[str, float]) -> str | None:
    best_day, best_distance = None, float("inf")
    for day, center in columns.items():
        distance = abs(line["cx"] - center)
        if distance < best_distance:
            best_day, best_distance = day, distance
    # Qua xa cot gan nhat nghia la dong nam ngoai bang, vi du tieu de lon.
    if best_day is None or best_distance > 140:
        return None
    return best_day


def _group_rows(
    lines: list[dict[str, Any]],
    columns: dict[str, float],
    grid_lines: list[float] | None = None,
) -> list[dict[str, list[dict[str, Any]]]]:
    """Gom chu theo tung hang cua mot bang, moi hang la mot tiet.

    Neu co duong ke thi cac hang duoc xac dinh bang duong ke, nho do hang
    rong hoan toan van duoc giu lai va so tiet khong bi lech. Khong co
    duong ke thi phai uoc luong khoang cach giua cac dong chu.
    """
    body: list[dict[str, Any]] = []
    for line in lines:
        if _assign_column(line, columns) is None:
            continue
        body.append(line)
    if not body:
        return []

    bands = _row_bands(body, grid_lines)
    if bands is None:
        return _group_rows_by_spacing(body, columns)

    grouped: list[dict[str, list[dict[str, Any]]]] = []
    for items in bands:
        # Bo dong nhan buoi. Tieu de thu va nhan buoi deu khong phai tiet hoc.
        items = [line for line in items if not _is_session_label(line["text"])]
        if not items:
            continue
        by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for line in items:
            day = _assign_column(line, columns)
            if day is not None:
                by_day[day].append(line)
        if not by_day:
            continue
        # Hang tieu de thu chi chua nhan thu, khong phai tiet hoc.
        if all(_key(line["text"]) in _DAY_KEY_SET for line in items):
            continue
        grouped.append({
            day: sorted(day_lines, key=lambda item: item["y1"]) for day, day_lines in by_day.items()
        })
    return grouped


def _is_session_label(text: str) -> bool:
    """Dò dòng tiêu đề buổi như "Buổi sáng - Thứ 2 chào cờ" hay "Buổi chiều"."""
    key = _key(text)
    if "buoi" not in key and "ca" not in key:
        return False
    return any(marker in key for markers in SESSION_MARKERS.values() for marker in markers)


def _row_bands(
    body: list[dict[str, Any]],
    grid_lines: list[float] | None,
) -> list[list[dict[str, Any]]] | None:
    """Chia chu theo các ô giữa những đường kẻ ngang, hoặc None nếu không có.

    Các đường kẻ của cả ảnh được chia thành từng đoạn liên tiếp, mỗi đoạn
    là một bảng. Nhờ vậy bảng buổi sáng và bảng buổi chiều không lẫn vào
    nhau dù chung toạ độ đường kẻ.
    """
    if not grid_lines or len(grid_lines) < 2:
        return None
    # Không lọc đường kẻ theo phạm vi chữ: bảng thật có những hàng trống
    # hoàn toàn, nếu lọc theo chữ thì mất đường kẻ ở các hàng đó.
    borders = list(grid_lines)
    if len(borders) < 2:
        return None

    gaps = [b - a for a, b in zip(borders, borders[1:])]
    # Khoảng cách lớn bất thường là ranh giới giữa hai bảng.
    if not gaps:
        return None
    typical = sorted(gaps)[len(gaps) // 2]
    breaks = [index for index, gap in enumerate(gaps) if gap > typical * 1.8]
    if not breaks:
        chunks = [borders]
    else:
        chunks = []
        start = 0
        for index in breaks:
            chunks.append(borders[start:index + 2])
            start = index + 1
        chunks.append(borders[start:])

    bands: list[list[dict[str, Any]]] = []
    for chunk in chunks:
        for position in range(len(chunk) - 1):
            band = [
                line for line in body if chunk[position] <= line["cy"] < chunk[position + 1]
            ]
            # Bỏ hàng rỗng hoàn toàn, không có chữ thì không có tiết học nào.
            if band:
                bands.append(band)
    return bands


def _group_rows_by_spacing(
    body: list[dict[str, Any]],
    columns: dict[str, float],
) -> list[dict[str, list[dict[str, Any]]]]:
    """Gom hàng khi ảnh không có đường kẻ rõ, dựa trên khoảng cách chữ."""
    row_gap = _row_gaps(body, None)
    buckets: dict[str, dict[str, Any]] = {}
    for line in sorted(body, key=lambda item: item["cy"]):
        best_row, best_distance = None, float("inf")
        for key, row in buckets.items():
            distance = abs(row["cy"] - line["cy"])
            if distance < best_distance:
                best_row, best_distance = key, distance
        if best_row is not None and best_distance < row_gap:
            row = buckets[best_row]
            row["lines"].append(line)
            row["cy"] = sum(item["cy"] for item in row["lines"]) / len(row["lines"])
        else:
            buckets[f"r{len(buckets)}"] = {"cy": line["cy"], "lines": [line]}

    grouped: list[dict[str, list[dict[str, Any]]]] = []
    for row in sorted(buckets.values(), key=lambda item: item["cy"]):
        by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for line in row["lines"]:
            day = _assign_column(line, columns)
            if day is not None:
                by_day[day].append(line)
        if by_day:
            grouped.append({
                day: sorted(items, key=lambda item: item["y1"]) for day, items in by_day.items()
            })
    return grouped


def _row_gaps(body: list[dict[str, Any]], grid_lines: list[float] | None) -> float:
    """Ngoai dung de ghep chu trong cung mot o vao mot hang khi khong co duong ke.

    Hai dong trong cung mot o cach nhau it, nen dung 2.5 lan chieu cao chu.
    """
    heights = [line["y2"] - line["y1"] for line in body if line["y2"] > line["y1"]]
    if not heights:
        return 24.0
    return max(20.0, 2.5 * sorted(heights)[len(heights) // 2])


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", _CLEAN.sub(" ", str(text or ""))).strip(" -\u2013\u2014")


def _format_subject(text: str) -> str:
    """Chuan hoa ten mon hoc, co giai chinh loai OCR gay sai ky tu."""
    clean = _clean_text(text)
    key = _key(clean)
    if key in SUBJECT_ALIASES:
        return SUBJECT_ALIASES[key]
    # OCR hay nhoi them ky tu la o cuoi ("LICH SUr") hoac sai mot ky tu.
    # Chi gan nhat khi do tuong doi cao, truoc khi hien thi tho.
    if len(key) >= 4:
        match = difflib.get_close_matches(key, SUBJECT_ALIASES.keys(), n=1, cutoff=0.85)
        if match:
            return SUBJECT_ALIASES[match[0]]
    return clean[:60]


def _format_lecturer(text: str) -> str:
    """Giao vien chi lam sach chu, khong ghep ten mon.

    Gom chung voi `_format_subject` se bien "T.Hoan" thanh mon "Toan".
    """
    return _clean_text(text)[:40]


def _parse_cell(items: list[dict[str, Any]]) -> tuple[str, str]:
    """Tach noi dung o thanh (mon hoc, giao vien).

    O duoc viet hai dong theo kieu "Toan" roi "T.Hoang" hoac "TAGT" roi
    "TAGT8", nen dong cuoi lai thuong la giao vien hoac ma mon.
    """
    ordered = sorted(items, key=lambda item: item["y1"])
    text = " ".join(item["text"] for item in ordered).strip()
    parts = [part for part in _SPLIT_ON_DASH.split(text) if part.strip()]
    if len(parts) >= 2:
        # Môn học có thể chứa dấu gạch nối riêng ("HDTN-SHDC"), phần sau
        # dấu gạch cuối mới là giáo viên. Ghép các phần trước lại làm môn.
        subject = "-".join(parts[:-1])
        return _format_subject(subject), _format_lecturer(parts[-1])
    if len(ordered) >= 2:
        return _format_subject(ordered[0]["text"]), _format_lecturer(ordered[-1]["text"])
    return _format_subject(text), ""


def extract_timetable_slots(
    image_bytes: bytes,
    max_periods_per_session: int = MAX_PERIODS_PER_SESSION,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Tra ve danh sach tiet hoc doc duoc tu anh va cac canh bao can hien thi.

    Anh thuc te co the co 6 tiet trong mot buoi, nhung thoi khoa bieu chi
    luu duoc tiet 1 den 5. Nhung tiet vuot gioi han duoc bo qua va
    thong bao de nguoi dung biet thay vi mat ngam.
    """
    lines, grid_lines = _read_lines(image_bytes)
    columns = _find_day_columns(lines)
    sessions = _split_sessions(lines)

    slots: list[dict[str, Any]] = []
    warnings: list[str] = []
    for session in ("morning", "afternoon"):
        rows = _group_rows(sessions.get(session, []), columns, grid_lines)
        if len(rows) > max_periods_per_session:
            warnings.append(
                f"{SESSION_LABELS[session]} có {len(rows)} tiết, "
                f"nhưng chỉ lưu được {max_periods_per_session} tiết nên đã bỏ "
                f"{len(rows) - max_periods_per_session} tiết cuối."
            )
        for period, row in enumerate(rows[:max_periods_per_session], start=1):
            for day, items in sorted(row.items()):
                subject, lecturer = _parse_cell(items)
                if not subject:
                    continue
                slots.append({
                    "session": session,
                    "day": day,
                    "period": period,
                    "subject": subject,
                    "lecturer": lecturer,
                })
    if not slots:
        raise TimetableImageError("Không nhận ra tiết học nào trong ảnh.")
    return slots, warnings


def timetable_ocr_available() -> bool:
    """Kiem tra xu co the doc anh o may chu hien tai hay khong."""
    try:
        import cv2  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True

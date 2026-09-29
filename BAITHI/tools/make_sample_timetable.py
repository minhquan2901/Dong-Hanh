"""Sinh ảnh thời khóa biểu mô phỏng để kiểm chứng pipeline OCR.

Bố cục giống ảnh thật: khối thông tin ở đầu, khối buổi sáng ở giữa,
khối buổi chiều ở dưới. Mỗi khối buổi có một dòng tiêu đề thứ rồi
đến các dòng tiết học. Dấu chấm là ô trống, "\n" là xuống dòng trong ô.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

DAY_LABELS = ["THỨ 2", "THỨ 3", "THỨ 4", "THỨ 5", "THỨ 6", "THỨ 7"]
MORNING = [
    ["HDTN-SHDC - L.\nM.Thành", "NNgữ - A.Thu Lan", "LS&ĐL - Đ.Trang", "Văn - V.Huyền", "GDDP - H.Lan", "."],
    ["HDTN-CĐ - L.M.Thành", "NNgữ - A.Thu Lan", "LS&ĐL - Đ.Trang", "Văn - V.Huyền", "Tin - Tin.Hùng - P.1_H", "."],
    ["Văn - V.Huyền", "Văn - V.Huyền", "AI/CDS - AI/CDS2", "LS&ĐL - Đ.Trang", "KHTN - L.M.Thành", "."],
    ["Toán - T.Hoàng", "GDTC - T.Kiên", "GDCD - CĐ.Hằng", "MT - MT.Tuyến", "KHTN - L.M.Thành", "."],
    ["Toán - T.Hoàng", "GDTC - T.Kiên", "Nhạc - Nhạc.Huy", "STEM - STEM 2", "C.Nghệ - CN.Chi", "."],
]
AFTERNOON = [
    [".", ".", ".", ".", ".", "."],
    ["TAGT - TAGT8", "THQT - Tin.Hùng -\nP.1_H", "Toán - T.Hoàng", "NNgữ - A.Thu Lan", "Toán - T.Hoàng", "."],
    ["TAGT - TAGT8", "THQT - Tin.Hùng -\nP.1_H", "KHTN - L.M.Thành", "ISMART - ISMART8", "HDTN-SHL - L.\nM.Thành", "."],
    ["ISMART - ISMART8", "ISMART - ISMART8", "KHTN - L.M.Thành", "ISMART - ISMART8", ".", "."],
    [".", ".", ".", ".", ".", "."],
]
INFO_BOX = [
    "THCS AN NHON  Tru so chinh",
    "Nam hoc 2026 - 2027",
    "Hoc ky 1",
]
INFO_CENTER = ["THOI KHOA BIEU", "Lop 8A2", "(Thuc hien tu ngay 14 thang 09 nam 2026)"]
INFO_RIGHT = ["So 2", "GVCN: Ho Mai Thanh"]
MORNING_TITLE = "Buoi sang - Thu 2 chao co tu 7h00-7h15"
AFTERNOON_TITLE = "Buoi chieu"

CELL_W, CELL_H, PAD = 205, 96, 60
FONT = cv2.FONT_HERSHEY_SIMPLEX


def build_image() -> np.ndarray:
    table_w = CELL_W * len(DAY_LABELS)
    width = table_w + PAD * 2
    canvas = np.full((1500, width, 3), 255, dtype=np.uint8)
    y = 40

    # Khối thông tin: một khung lớn chia ba cột.
    info_h = 110
    cv2.rectangle(canvas, (PAD, y), (PAD + table_w, y + info_h), (70, 70, 70), 2)
    for index, line in enumerate(INFO_BOX):
        cv2.putText(canvas, line, (PAD + 12, y + 26 + index * 26), FONT, 0.5, (0, 0, 0), 1)
    for index, line in enumerate(INFO_CENTER):
        size = 0.9 if index == 0 else 0.6
        thickness = 2 if index == 0 else 1
        cv2.putText(canvas, line, (PAD + table_w // 3, y + 40 + index * 26), FONT, size, (0, 0, 0), thickness)
    for index, line in enumerate(INFO_RIGHT):
        cv2.putText(canvas, line, (PAD + table_w - 220, y + 45 + index * 28), FONT, 0.6, (0, 0, 0), 1)
    y += info_h + 40

    for title, rows in ((MORNING_TITLE, MORNING), (AFTERNOON_TITLE, AFTERNOON)):
        cv2.putText(canvas, title, (PAD, y + 18), FONT, 0.8, (0, 0, 0), 2)
        y += 32
        # Dòng tiêu đề thứ.
        for index, label in enumerate(DAY_LABELS):
            x0 = PAD + index * CELL_W
            cv2.rectangle(canvas, (x0, y), (x0 + CELL_W, y + 38), (70, 70, 70), 2)
            cv2.putText(canvas, label, (x0 + 58, y + 26), FONT, 0.55, (0, 0, 0), 1)
        y += 38
        for row in rows:
            for col_index, cell in enumerate(row):
                x0 = PAD + col_index * CELL_W
                cv2.rectangle(canvas, (x0, y), (x0 + CELL_W, y + CELL_H), (70, 70, 70), 2)
                if cell == ".":
                    continue
                text_y = y + CELL_H // 2 - (cell.count("\n") * 15)
                for line in cell.split("\n"):
                    cv2.putText(canvas, line, (x0 + 10, text_y), FONT, 0.5, (0, 0, 0), 1)
                    text_y += 28
            y += CELL_H
        y += 40

    return canvas[:y + 20, :]


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "tools/sample_timetable.png")
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), build_image())
    print(target.resolve())

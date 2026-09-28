"""Sinh icon PNG cho PWA.

PWA tren Android va iOS yeu cau icon PNG; Safari khong dung SVG cho icon
tren man hinh chinh. File nay ve lai icon bang Pillow de tao cac kich thuoc
chu cho manifest, giu dung hinh dang nhu ban SVG goc.

Chay: python make_pwa_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "static"

SIZES = {
    "icon-72.png": 72,
    "icon-96.png": 96,
    "icon-128.png": 128,
    "icon-144.png": 144,
    "icon-152.png": 152,
    "icon-192.png": 192,
    "icon-512.png": 512,
    "apple-touch-icon.png": 180,
    "studysync-icon-v2-72.png": 72,
    "studysync-icon-v2-96.png": 96,
    "studysync-icon-v2-128.png": 128,
    "studysync-icon-v2-144.png": 144,
    "studysync-icon-v2-152.png": 152,
    "studysync-icon-v2-180.png": 180,
    "studysync-icon-v2-192.png": 192,
    "studysync-icon-v2-512.png": 512,
    "studysync-apple-touch-icon-v2.png": 180,
    "studysync-icon-maskable-v2-192.png": 192,
    "studysync-icon-maskable-v2-512.png": 512,
}

# Mau lay theo file SVG goc.
BLUE = (37, 99, 235)
TEAL = (15, 159, 154)
AMBER = (251, 191, 36)


def lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def draw_icon(size: int) -> Image.Image:
    """Ve icon vu: nen gradient, vong tron vang, chu S, bo tron goc.

    Ve o kich thuoc gap gap roi thu nho de bo goc va chu khong bi rang cua.
    """
    scale = 4
    big = size * scale
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Nen gradient: goc tren ben trai BLUE, goc duoi ben phai TEAL.
    last = max(big - 1, 1)
    for y in range(big):
        t = y / last
        row = []
        for x in range(big):
            u = (x / last + t) / 2
            row.append(
                (
                    lerp(BLUE[0], TEAL[0], u),
                    lerp(BLUE[1], TEAL[1], u),
                    lerp(BLUE[2], TEAL[2], u),
                    255,
                )
            )
        draw.line([(0, y), (big - 1, y)], fill=row[-1])
        for x in range(big):
            image.putpixel((x, y), row[x])

    # Vong tron vang o goc tren ben phai.
    sun_r = round(big * 12 / 128)
    sun_cx = round(big * 96 / 128)
    sun_cy = round(big * 30 / 128)
    draw.ellipse(
        [sun_cx - sun_r, sun_cy - sun_r, sun_cx + sun_r, sun_cy + sun_r],
        fill=(AMBER[0], AMBER[1], AMBER[2], 242),
    )

    # Chu S, dung font mac dinh cua Pillow de khong can file font ngoai.
    font = ImageFont.load_default(size=round(big * 0.66))
    left, top, right, bottom = draw.textbbox((0, 0), "S", font=font)
    draw.text(
        ((big - (right - left)) / 2 - left, (big - (bottom - top)) / 2 - top),
        "S",
        font=font,
        fill=(255, 255, 255, 255),
    )

    # Bo tron goc nhu ban SVG goc (rx = 30/128).
    radius = round(big * 30 / 128)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, big - 1, big - 1], radius=radius, fill=255
    )
    image.putalpha(mask)

    return image.resize((size, size), Image.LANCZOS)


def draw_icon_v2(size: int, maskable: bool = False) -> Image.Image:
    """Draw a refreshed StudySync mark with a bold monogram and study spark."""
    scale = 4
    big = size * scale
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    last = max(big - 1, 1)

    for y in range(big):
        t = y / last
        left = (24, 91, 216)
        right = (13, 153, 151)
        color = tuple(lerp(left[i], right[i], t) for i in range(3)) + (255,)
        draw.line([(0, y), (big - 1, y)], fill=color)

    font_size = round(big * 0.62)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
    except OSError:
        font = ImageFont.load_default(size=font_size)
    bounds = draw.textbbox((0, 0), "S", font=font, stroke_width=0)
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    draw.text(
        ((big - text_width) / 2 - bounds[0] - big * 0.025,
         (big - text_height) / 2 - bounds[1] + big * 0.035),
        "S",
        font=font,
        fill=(255, 255, 255, 255),
    )

    spark_x = round(big * 0.76)
    spark_y = round(big * 0.24)
    spark_radius = round(big * 0.105)
    draw.ellipse(
        [spark_x - spark_radius, spark_y - spark_radius,
         spark_x + spark_radius, spark_y + spark_radius],
        fill=(255, 203, 64, 255),
    )
    draw.ellipse(
        [spark_x - spark_radius * 0.48, spark_y - spark_radius * 0.48,
         spark_x + spark_radius * 0.48, spark_y + spark_radius * 0.48],
        fill=(255, 232, 153, 255),
    )

    radius = round(big * 30 / 128)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, big - 1, big - 1], radius=radius, fill=255
    )
    if not maskable:
        image.putalpha(mask)
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, size in SIZES.items():
        target = OUT_DIR / filename
        if "maskable-v2" in filename or "apple-touch-icon-v2" in filename:
            icon = draw_icon_v2(size, maskable=True)
        else:
            icon = draw_icon_v2(size) if "v2" in filename else draw_icon(size)
        icon.save(target, format="PNG", optimize=True)
        print(f"  + {target.name} ({size}x{size})")
    print(f"\nDa tao {len(SIZES)} icon trong {OUT_DIR}")


if __name__ == "__main__":
    main()

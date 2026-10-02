from backend.schedule_ocr import _target_ocr_dimensions


def test_small_timetable_image_is_not_upscaled():
    assert _target_ocr_dimensions(1075, 767) == (1075, 767)


def test_large_timetable_image_is_downscaled_without_changing_aspect_ratio():
    assert _target_ocr_dimensions(3200, 1600) == (1600, 800)

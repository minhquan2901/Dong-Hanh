from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from backend import timetable_ai
from auth_service import register_user
from owner_auth import create_user_token
from web_app import app


def test_normalize_gemini_timetable_json():
    slots, warnings = timetable_ai._normalize_result({
        "slots": [{
            "session": "morning",
            "day": "Thứ 2",
            "period": 1,
            "subject": "Toán",
            "lecturer": "Cô Lan",
        }],
        "warnings": [],
    })

    assert slots == [{
        "session": "morning",
        "day": "2",
        "period": 1,
        "subject": "Toán",
        "lecturer": "Cô Lan",
    }]
    assert warnings == []


def test_normalize_rejects_period_out_of_range():
    with pytest.raises(timetable_ai.TimetableAIError):
        timetable_ai._normalize_result({
            "slots": [{
                "session": "morning", "day": "2", "period": 99,
                "subject": "Toán", "lecturer": "",
            }],
            "warnings": [],
        })


def test_missing_gemini_key_returns_configuration_error(monkeypatch):
    monkeypatch.delenv("TIMETABLE_GEMINI_API_KEY", raising=False)

    with pytest.raises(timetable_ai.TimetableAIError) as error:
        timetable_ai.extract_timetable_slots_from_image(b"image", "image/png")

    assert error.value.status_code == 503
    assert "TIMETABLE_GEMINI_API_KEY" in str(error.value)


def test_gemini_request_sends_inline_image_and_structured_output(monkeypatch):
    monkeypatch.setenv("TIMETABLE_GEMINI_API_KEY", "test-key")
    captured = {}
    result = {"slots": [{
        "session": "afternoon", "day": "7", "period": 2,
        "subject": "KHTN", "lecturer": "Thầy Nam",
    }], "warnings": []}

    class Response:
        status_code = 200

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(result)}]}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(timetable_ai.requests, "post", fake_post)
    slots, warnings = timetable_ai.extract_timetable_slots_from_image(b"sample", "image/png")

    assert captured["url"].endswith("/models/gemini-3.8-flash:generateContent")
    assert captured["headers"]["x-goog-api-key"] == "test-key"
    part = captured["json"]["contents"][0]["parts"][1]["inlineData"]
    assert part["mimeType"] == "image/png"
    assert base64.b64decode(part["data"]) == b"sample"
    assert captured["json"]["generationConfig"]["responseFormat"]["text"]["mimeType"] == "APPLICATION_JSON"
    assert slots[0]["subject"] == "KHTN"
    assert warnings == []


@pytest.fixture
def student_client(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr("database.study_repository.data_file", lambda name: tmp_path / name)
    monkeypatch.setenv("STUDYSYNC_SESSION_SECRET", "test-session-secret-with-at-least-32-chars")
    register_user("student_ai", "Pass1234", "student", "Học sinh AI", "8/1")
    token = create_user_token("student_ai", "student")
    return TestClient(app), {
        "Authorization": f"Bearer {token}",
        "X-Username": "student_ai",
    }


def test_timetable_image_status_tracks_gemini_key(monkeypatch):
    client = TestClient(app)
    monkeypatch.delenv("TIMETABLE_GEMINI_API_KEY", raising=False)
    assert client.get("/api/schedule/import-image/status").json() == {"available": False}
    monkeypatch.setenv("TIMETABLE_GEMINI_API_KEY", "test-key")
    assert client.get("/api/schedule/import-image/status").json() == {"available": True}


def test_timetable_image_requires_student_session(student_client, monkeypatch):
    client, _ = student_client
    monkeypatch.setenv("TIMETABLE_GEMINI_API_KEY", "test-key")
    response = client.post(
        "/api/schedule/import-image",
        files={"file": ("schedule.png", b"image", "image/png")},
    )
    assert response.status_code == 403


def test_timetable_image_requires_gemini_key(student_client, monkeypatch):
    client, headers = student_client
    monkeypatch.delenv("TIMETABLE_GEMINI_API_KEY", raising=False)
    response = client.post(
        "/api/schedule/import-image",
        headers=headers,
        files={"file": ("schedule.png", b"image", "image/png")},
    )
    assert response.status_code == 503
    assert "TIMETABLE_GEMINI_API_KEY" in response.json()["detail"]


def test_timetable_image_returns_preview_without_saving(student_client, monkeypatch):
    from bus.study_bus import StudyBus
    import web_app

    client, headers = student_client
    monkeypatch.setenv("TIMETABLE_GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(web_app, "extract_timetable_slots_from_image", lambda image, mime: (
        [{"session": "morning", "day": "2", "period": 1, "subject": "Toán", "lecturer": "Cô Lan"}],
        [],
    ))
    response = client.post(
        "/api/schedule/import-image",
        headers=headers,
        files={"file": ("schedule.png", b"image", "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["slots"][0]["username"] == "student_ai"
    assert StudyBus().schedule("student_ai") == []
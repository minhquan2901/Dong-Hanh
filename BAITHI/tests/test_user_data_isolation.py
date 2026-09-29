from __future__ import annotations

from fastapi.testclient import TestClient

from auth_service import assign_student_to_parent, register_user
from web_app import app


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["token"]


def test_students_only_see_and_mutate_their_own_schedule_and_assignments(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr("database.study_repository.data_file", lambda name: tmp_path / name)
    monkeypatch.setattr("owner_service.USAGE_FILE", tmp_path / "feature_usage.json")
    monkeypatch.setenv("STUDYSYNC_SESSION_SECRET", "test-session-secret-for-user-isolation")

    register_user("student_a", "StudentPass1", "student", "Học sinh A", "8/1")
    register_user("student_b", "StudentPass2", "student", "Học sinh B", "8/2")
    client = TestClient(app)
    token_a = _login(client, "student_a", "StudentPass1")
    token_b = _login(client, "student_b", "StudentPass2")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    for username, subject, headers in (
        ("student_a", "Toán của A", headers_a),
        ("student_b", "Văn của B", headers_b),
    ):
        response = client.post("/api/schedule/slots", headers=headers, json={"slots": [{
            "session": "morning", "day": "2", "period": 1,
            "subject": subject, "lecturer": "GV", "username": username,
        }]})
        assert response.status_code == 200
        task = client.post("/api/assignments", headers=headers, json={
            "title": f"Bài {username}", "subject": "Môn", "due_date": "2026-10-01",
            "priority": "Cao", "username": username,
        })
        assert task.status_code == 200

    dashboard_a = client.get("/api/dashboard/student?username=student_a", headers=headers_a).json()
    dashboard_b = client.get("/api/dashboard/student?username=student_b", headers=headers_b).json()
    assert [item["subject"] for item in dashboard_a["schedule"]] == ["Toán của A"]
    assert [item["subject"] for item in dashboard_b["schedule"]] == ["Văn của B"]
    assert [item["title"] for item in dashboard_a["assignments"]] == ["Bài student_a"]
    assert [item["title"] for item in dashboard_b["assignments"]] == ["Bài student_b"]

    task_a_id = dashboard_a["assignments"][0]["id"]
    assert client.patch(
        f"/api/assignments/{task_a_id}", headers=headers_b,
        json={"username": "student_b", "completed": True},
    ).status_code == 404
    assert client.delete(
        f"/api/assignments/{task_a_id}?username=student_b", headers=headers_b,
    ).status_code == 404


def test_parent_dashboard_aggregates_only_linked_students_owned_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr("auth_service.USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr("database.study_repository.data_file", lambda name: tmp_path / name)
    monkeypatch.setattr("owner_service.USAGE_FILE", tmp_path / "feature_usage.json")
    monkeypatch.setenv("STUDYSYNC_SESSION_SECRET", "test-session-secret-for-parent-scope")

    register_user("parent_a", "ParentPass1", "parent", "Phụ huynh A")
    student_a = register_user("student_a", "StudentPass1", "student", "Học sinh A", "8/1")
    student_b = register_user("student_b", "StudentPass2", "student", "Học sinh B", "8/2")
    register_user("student_c", "StudentPass3", "student", "Học sinh C", "8/3")
    assign_student_to_parent("parent_a", "student_a")
    assign_student_to_parent("parent_a", "student_b")

    client = TestClient(app)
    token_a = _login(client, "student_a", "StudentPass1")
    token_b = _login(client, "student_b", "StudentPass2")
    parent_token = _login(client, "parent_a", "ParentPass1")
    client.post("/api/assignments", headers={"Authorization": f"Bearer {token_a}"}, json={
        "title": "Bài A", "subject": "Toán", "due_date": "2026-10-01", "priority": "Cao", "username": student_a["username"],
    })
    client.post("/api/assignments", headers={"Authorization": f"Bearer {token_b}"}, json={
        "title": "Bài B", "subject": "Văn", "due_date": "2026-10-01", "priority": "Cao", "username": student_b["username"],
    })

    response = client.get(
        "/api/dashboard/parent?username=parent_a",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert {task["title"] for task in data["tasks"]} == {"Bài A", "Bài B"}
    assert {task["student_name"] for task in data["tasks"]} == {"Học sinh A", "Học sinh B"}
    assert data["overview"]["total_students"] == 2

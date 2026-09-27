from functools import partial
from http.server import ThreadingHTTPServer
import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import app


@pytest.fixture
def account_server(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.setattr(app, "PROJECT_DIR", project_dir)
    student_file = tmp_path / "accounts2.json"
    parent_file = tmp_path / "accounts3.json"
    monkeypatch.setattr(app, "STUDENT_ACCOUNTS_FILE", student_file)
    monkeypatch.setattr(app, "PARENT_ACCOUNTS_FILE", parent_file)
    monkeypatch.setattr(app, "ACCOUNTS_FILE", tmp_path / "accounts.json")

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(app.AppRequestHandler, directory=str(app.PROJECT_DIR)),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()
    server.server_close()


def post_json(base_url, path, payload):
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_student_and_parent_accounts_persist_separately(account_server, tmp_path):
    assert post_json(account_server, "/api/register", {
        "username": "student01",
        "password": "Student123",
        "role": "student",
    })[0] == 201
    assert post_json(account_server, "/api/register", {
        "username": "parent01",
        "password": "Parent123",
        "role": "parent",
    })[0] == 201

    students = json.loads((tmp_path / "accounts2.json").read_text(encoding="utf-8"))
    parents = json.loads((tmp_path / "accounts3.json").read_text(encoding="utf-8"))
    assert [item["username"] for item in students["accounts"]] == ["student01"]
    assert [item["username"] for item in parents["accounts"]] == ["parent01"]

    status, result = post_json(account_server, "/api/login", {
        "username": "student01",
        "password": "Student123",
    })
    assert status == 200
    assert result["role"] == "user"


@pytest.mark.parametrize("account_path", [
    "/TaiKhoan/accounts2.json",
    "/taikhoan/accounts2.json",
    "/%54aiKhoan/accounts2.json",
    "/TaiKhoan%2Faccounts2.json",
])
def test_account_files_are_not_served_as_static_files(account_server, account_path):
    with pytest.raises(HTTPError) as error:
        urlopen(f"{account_server}{account_path}")

    assert error.value.code == 404


def test_corrupt_account_file_is_not_treated_as_empty(tmp_path, monkeypatch):
    account_file = tmp_path / "accounts2.json"
    account_file.write_text('{"accounts": [', encoding="utf-8")
    monkeypatch.setattr(app, "STUDENT_ACCOUNTS_FILE", account_file)

    with pytest.raises(RuntimeError, match="Tệp tài khoản bị lỗi JSON"):
        app.load_accounts(account_file)

    assert account_file.read_text(encoding="utf-8") == '{"accounts": ['


def test_account_file_migrates_to_configured_persistent_directory(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    legacy_dir = project_dir / "TaiKhoan"
    persistent_dir = tmp_path / "persistent"
    legacy_dir.mkdir(parents=True)
    legacy_file = legacy_dir / "accounts2.json"
    legacy_file.write_text(json.dumps({
        "accounts": [{"username": "legacy-student", "password": "kept"}],
    }), encoding="utf-8")
    target_file = persistent_dir / "accounts2.json"
    monkeypatch.setattr(app, "PROJECT_DIR", project_dir)

    accounts = app.load_accounts(target_file)

    assert accounts["accounts"][0]["username"] == "legacy-student"
    assert json.loads(target_file.read_text(encoding="utf-8")) == accounts
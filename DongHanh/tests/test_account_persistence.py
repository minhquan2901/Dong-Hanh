from functools import partial
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

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


def test_account_cache_is_invalidated_after_save(tmp_path):
    account_file = tmp_path / "accounts.json"
    app.save_accounts({"accounts": [{"username": "student01", "display_name": "Tên cũ"}]}, account_file)

    loaded_accounts = app.load_accounts(account_file)
    loaded_accounts["accounts"][0]["display_name"] = "Không được ghi ngược vào cache"
    assert app.load_accounts(account_file)["accounts"][0]["display_name"] == "Tên cũ"

    app.save_accounts({"accounts": [{"username": "student01", "display_name": "Tên mới"}]}, account_file)
    assert app.load_accounts(account_file)["accounts"][0]["display_name"] == "Tên mới"


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


def test_registered_password_is_hashed_at_rest(account_server, tmp_path):
    assert post_json(account_server, "/api/register", {
        "username": "secure-student",
        "password": "Student123",
        "role": "student",
    })[0] == 201

    student_data = json.loads((tmp_path / "accounts2.json").read_text(encoding="utf-8"))
    stored_password = student_data["accounts"][0]["password"]
    assert stored_password.startswith("pbkdf2_sha256$")
    assert stored_password != "Student123"


def test_legacy_password_is_upgraded_after_successful_login(account_server, tmp_path):
    account_file = tmp_path / "accounts2.json"
    account_file.write_text(json.dumps({
        "accounts": [{
            "username": "legacy-student",
            "password": "Student123",
            "role": "user",
            "is_active": True,
        }]
    }), encoding="utf-8")
    with pytest.raises(HTTPError) as error:
        post_json(account_server, "/api/login", {
            "username": "legacy-student",
            "password": "wrong-password",
        })
    assert error.value.code == 401
    assert json.loads(account_file.read_text(encoding="utf-8"))["accounts"][0]["password"] == "Student123"

    status, result = post_json(account_server, "/api/login", {
        "username": "legacy-student",
        "password": "Student123",
    })

    assert status == 200
    assert result["username"] == "legacy-student"
    stored_accounts = json.loads(account_file.read_text(encoding="utf-8"))["accounts"]
    assert stored_accounts[0]["password"].startswith("pbkdf2_sha256$")


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


@pytest.mark.parametrize("private_path", [
    "/app.py",
    "/.env",
    "/Login/../app.py",
    "/%2e%2e/app.py",
])
def test_private_project_files_are_not_served(account_server, tmp_path, private_path):
    project_dir = tmp_path / "project"
    (project_dir / "app.py").write_text("private source", encoding="utf-8")
    (project_dir / ".env").write_text("PRIVATE=value", encoding="utf-8")

    with pytest.raises(HTTPError) as error:
        urlopen(f"{account_server}{private_path}")

    assert error.value.code == 404


def test_login_is_public_and_role_pages_require_session(account_server, tmp_path):
    project_dir = tmp_path / "project"
    (project_dir / "Login").mkdir()
    (project_dir / "Login" / "index.html").write_text("login page", encoding="utf-8")
    (project_dir / "Main").mkdir()
    (project_dir / "Main" / "index.html").write_text("student dashboard", encoding="utf-8")
    (project_dir / "Chucnang").mkdir()
    (project_dir / "Chucnang" / "thoi_khoa_bieu.html").write_text("schedule", encoding="utf-8")
    (project_dir / "Chucnang" / "thong_tin_ca_nhan.html").write_text("profile", encoding="utf-8")
    (project_dir / "ChucnangPH.html").write_text("parent dashboard", encoding="utf-8")

    for path, expected in (
        ("/", "login page"),
        ("/Login/", "login page"),
    ):
        with urlopen(f"{account_server}{path}") as response:
            assert response.status == 200
            assert response.read().decode("utf-8") == expected

    for path in ("/Main/", "/ChucnangPH.html", "/Chucnang/thoi_khoa_bieu.html?view=parent", "/Chucnang/thong_tin_ca_nhan.html"):
        with urlopen(f"{account_server}{path}") as response:
            assert response.geturl().endswith("/Login/")
            assert response.read().decode("utf-8") == "login page"

    with urlopen(Request(f"{account_server}/Main/index.html", method="HEAD")) as response:
        assert response.status == 200


def test_student_dashboard_requires_server_session(account_server, tmp_path):
    project_dir = tmp_path / "project"
    (project_dir / "Login").mkdir()
    (project_dir / "Login" / "index.html").write_text("login page", encoding="utf-8")
    (project_dir / "Main").mkdir()
    (project_dir / "Main" / "index.html").write_text("student dashboard", encoding="utf-8")

    with urlopen(f"{account_server}/Main/") as response:
        assert response.geturl().endswith("/Login/")
        assert response.read().decode("utf-8") == "login page"


def test_login_creates_http_only_session_and_session_api_returns_role(account_server):
    post_json(account_server, "/api/register", {
        "username": "session-parent",
        "password": "Parent123",
        "role": "parent",
    })
    client = build_opener(HTTPCookieProcessor(CookieJar()))
    login_request = Request(
        f"{account_server}/api/login",
        data=json.dumps({"username": "session-parent", "password": "Parent123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with client.open(login_request) as response:
        assert response.status == 200
        cookie_header = response.headers.get("Set-Cookie", "")
        assert "HttpOnly" in cookie_header
        assert "SameSite=Lax" in cookie_header

    with client.open(f"{account_server}/api/session") as response:
        assert json.loads(response.read().decode("utf-8"))["role"] == "parent"


@pytest.mark.parametrize(("role", "denied_path", "allowed_path", "allowed_text"), [
    ("parent", "/Main/", "/ChucnangPH.html", "parent dashboard"),
    ("student", "/ChucnangPH.html", "/Main/", "student dashboard"),
])
def test_session_role_guards_pages(account_server, tmp_path, role, denied_path, allowed_path, allowed_text):
    project_dir = tmp_path / "project"
    (project_dir / "Login").mkdir()
    (project_dir / "Login" / "index.html").write_text("login page", encoding="utf-8")
    (project_dir / "Main").mkdir()
    (project_dir / "Main" / "index.html").write_text("student dashboard", encoding="utf-8")
    (project_dir / "ChucnangPH.html").write_text("parent dashboard", encoding="utf-8")
    post_json(account_server, "/api/register", {
        "username": f"{role}-guard",
        "password": "Student123",
        "role": role,
    })
    client = build_opener(HTTPCookieProcessor(CookieJar()))
    login_request = Request(
        f"{account_server}/api/login",
        data=json.dumps({"username": f"{role}-guard", "password": "Student123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    client.open(login_request).close()

    with pytest.raises(HTTPError) as error:
        client.open(f"{account_server}{denied_path}")
    assert error.value.code == 403
    with client.open(f"{account_server}{allowed_path}") as response:
        assert response.read().decode("utf-8") == allowed_text


def test_logout_invalidates_server_session(account_server):
    post_json(account_server, "/api/register", {
        "username": "logout-parent",
        "password": "Parent123",
        "role": "parent",
    })
    client = build_opener(HTTPCookieProcessor(CookieJar()))
    login_request = Request(
        f"{account_server}/api/login",
        data=json.dumps({"username": "logout-parent", "password": "Parent123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    client.open(login_request).close()
    with client.open(f"{account_server}/api/session") as response:
        assert response.status == 200
        csrf_token = json.loads(response.read().decode("utf-8"))["csrf_token"]

    with pytest.raises(HTTPError) as error:
        client.open(Request(f"{account_server}/api/logout", data=b"", method="POST"))
    assert error.value.code == 403

    with client.open(Request(
        f"{account_server}/api/logout",
        data=b"",
        headers={"X-CSRF-Token": csrf_token},
        method="POST",
    )) as response:
        assert response.status == 200
    with pytest.raises(HTTPError) as error:
        client.open(f"{account_server}/api/session")
    assert error.value.code == 401


def test_security_headers_are_present_on_public_pages(account_server, tmp_path):
    login_dir = tmp_path / "project" / "Login"
    login_dir.mkdir()
    (login_dir / "index.html").write_text("login page", encoding="utf-8")

    with urlopen(account_server) as response:
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Content-Security-Policy" in response.headers


def test_create_server_skips_loopback_port_already_in_use(monkeypatch):
    with ThreadingHTTPServer(("127.0.0.1", 0), app.AppRequestHandler) as occupied_server:
        monkeypatch.setattr(app, "PORT", occupied_server.server_port)
        monkeypatch.setattr(app, "MAX_PORT_ATTEMPTS", 2)
        server = app.create_server(app.AppRequestHandler)
        try:
            assert server.server_port == occupied_server.server_port + 1
        finally:
            server.server_close()


def test_oversized_auth_request_is_rejected(account_server):
    request = Request(
        f"{account_server}/api/register",
        data=(b'{"username":"' + b"a" * 16_384 + b'","password":"Student123"}'),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    assert error.value.code == 413


def test_oversized_logout_request_is_rejected(account_server):
    request = Request(
        f"{account_server}/api/logout",
        data=b"x" * 16_385,
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    assert error.value.code == 413


def test_cross_origin_auth_write_is_rejected(account_server):
    request = Request(
        f"{account_server}/api/register",
        data=json.dumps({
            "username": "cross-origin",
            "password": "Student123",
            "role": "student",
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": "https://attacker.example"},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    assert error.value.code == 403


def test_login_is_rate_limited_after_repeated_failures(account_server):
    post_json(account_server, "/api/register", {
        "username": "limited-student",
        "password": "Student123",
        "role": "student",
    })
    for _ in range(5):
        with pytest.raises(HTTPError) as error:
            post_json(account_server, "/api/login", {
                "username": "limited-student",
                "password": "wrong-password",
            })
        assert error.value.code == 401

    with pytest.raises(HTTPError) as error:
        post_json(account_server, "/api/login", {
            "username": "limited-student",
            "password": "wrong-password",
        })
    assert error.value.code == 429


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
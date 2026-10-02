import base64
from copy import deepcopy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import os
import posixpath
from pathlib import Path
import secrets
import shutil
import socket
import tempfile
import time
from threading import RLock
from http.cookies import SimpleCookie
from urllib.parse import unquote, urlsplit
import webbrowser


PROJECT_DIR = Path(__file__).resolve().parent
HOST = "0.0.0.0"
PORT = 8000
MAX_PORT_ATTEMPTS = 10
ACCOUNT_DATA_DIR = Path(
	os.environ.get("DONGHANH_DATA_DIR", PROJECT_DIR / "TaiKhoan")
).expanduser()
ACCOUNTS_FILE = ACCOUNT_DATA_DIR / "accounts.json"
STUDENT_ACCOUNTS_FILE = ACCOUNT_DATA_DIR / "accounts2.json"
PARENT_ACCOUNTS_FILE = ACCOUNT_DATA_DIR / "accounts3.json"
ACCOUNT_LOCK = RLock()
ACCOUNT_CACHE_LOCK = RLock()
ACCOUNT_CACHE: dict[Path, tuple[int, int, dict]] = {}
PASSWORD_ITERATIONS = 200_000
PASSWORD_PREFIX = "pbkdf2_sha256$"
SESSION_COOKIE_NAME = "donghanh_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
SESSION_SECRET = os.environ.get("DONGHANH_SESSION_SECRET", "").encode("utf-8") or secrets.token_bytes(32)
MAX_REQUEST_BODY_BYTES = 16_384
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 300
LOGIN_FAILURES: dict[tuple[str, str], list[float]] = {}
LOGIN_FAILURES_LOCK = RLock()
PUBLIC_STATIC_PATHS = {
	path.casefold(): path
	for path in (
		"/Login/",
		"/Login/index.html",
		"/Main/",
		"/Main/index.html",
		"/ChucnangPH.html",
		"/Chucnang/thoi_khoa_bieu.html",
		"/Chucnang/thong_tin_ca_nhan.html",
	)
}


def _migrate_legacy_account_file(file_path: Path) -> None:
	legacy_path = PROJECT_DIR / "TaiKhoan" / file_path.name
	if file_path == legacy_path or file_path.exists() or not legacy_path.is_file():
		return
	file_path.parent.mkdir(parents=True, exist_ok=True)
	temporary_path = file_path.with_name(f".{file_path.name}.migration.tmp")
	try:
		shutil.copy2(legacy_path, temporary_path)
		os.replace(temporary_path, file_path)
	finally:
		temporary_path.unlink(missing_ok=True)



def load_accounts(file_path: Path | None = None) -> dict:
	file_path = Path(file_path or ACCOUNTS_FILE).resolve()
	_migrate_legacy_account_file(file_path)
	try:
		file_stat = file_path.stat()
	except FileNotFoundError:
		return {"accounts": []}
	cache_signature = (file_stat.st_mtime_ns, file_stat.st_size)
	with ACCOUNT_CACHE_LOCK:
		cached = ACCOUNT_CACHE.get(file_path)
		if cached and cached[:2] == cache_signature:
			return deepcopy(cached[2])
	try:
		with file_path.open("r", encoding="utf-8") as file:
			data = json.load(file)
	except json.JSONDecodeError as exc:
		raise RuntimeError(f"Tệp tài khoản bị lỗi JSON: {file_path}") from exc
	if not isinstance(data, dict) or not isinstance(data.get("accounts", []), list):
		raise RuntimeError(f"Cấu trúc tệp tài khoản không hợp lệ: {file_path}")
	with ACCOUNT_CACHE_LOCK:
		ACCOUNT_CACHE[file_path] = (*cache_signature, deepcopy(data))
	return data


def save_accounts(data: dict, file_path: Path | None = None) -> None:
	file_path = Path(file_path or ACCOUNTS_FILE).resolve()
	file_path.parent.mkdir(parents=True, exist_ok=True)
	with tempfile.NamedTemporaryFile(
		mode="w", encoding="utf-8", dir=file_path.parent,
		prefix=f".{file_path.name}.", suffix=".tmp", delete=False,
	) as file:
		temporary_path = Path(file.name)
		json.dump(data, file, ensure_ascii=False, indent=2)
		file.flush()
		os.fsync(file.fileno())
	os.replace(temporary_path, file_path)
	with ACCOUNT_CACHE_LOCK:
		ACCOUNT_CACHE.pop(file_path, None)


def hash_password(password: str) -> str:
	salt = secrets.token_bytes(16)
	digest = hashlib.pbkdf2_hmac(
		"sha256", str(password).encode("utf-8"), salt, PASSWORD_ITERATIONS
	)
	return f"{PASSWORD_PREFIX}{salt.hex()}${digest.hex()}"


def verify_password(stored_password: str, candidate: str) -> bool:
	stored = str(stored_password or "")
	if not stored.startswith(PASSWORD_PREFIX):
		return hmac.compare_digest(stored, str(candidate or ""))
	try:
		_, salt_hex, expected_hex = stored.split("$", 2)
		salt = bytes.fromhex(salt_hex)
		expected = bytes.fromhex(expected_hex)
	except (TypeError, ValueError):
		return False
	actual = hashlib.pbkdf2_hmac(
		"sha256", str(candidate or "").encode("utf-8"), salt, PASSWORD_ITERATIONS
	)
	return hmac.compare_digest(actual, expected)


def create_session_token(username: str, now: int | None = None) -> str:
	payload = json.dumps({
		"username": username,
		"expires_at": (int(time.time()) if now is None else now) + SESSION_TTL_SECONDS,
		"csrf_token": secrets.token_urlsafe(32),
	}, separators=(",", ":")).encode("utf-8")
	encoded_payload = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
	signature = hmac.new(SESSION_SECRET, encoded_payload.encode("ascii"), hashlib.sha256).hexdigest()
	return f"{encoded_payload}.{signature}"


def read_session_payload(token: str, now: int | None = None) -> dict | None:
	try:
		encoded_payload, signature = token.split(".", 1)
		expected_signature = hmac.new(
			SESSION_SECRET, encoded_payload.encode("ascii"), hashlib.sha256
		).hexdigest()
		if not hmac.compare_digest(signature, expected_signature):
			return None
		payload_bytes = base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4))
		payload = json.loads(payload_bytes.decode("utf-8"))
		current_time = int(time.time()) if now is None else now
		if int(payload.get("expires_at", 0)) <= current_time:
			return None
		return payload if isinstance(payload, dict) else None
	except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
		return None


def read_session_username(token: str, now: int | None = None) -> str | None:
	payload = read_session_payload(token, now)
	username = str(payload.get("username", "")).strip() if payload else ""
	return username or None


def get_account_file_for_role(role: str) -> Path:
	if role in ("student", "user"):
		return STUDENT_ACCOUNTS_FILE
	if role == "parent":
		return PARENT_ACCOUNTS_FILE
	return ACCOUNTS_FILE


def find_account_by_username(username: str):
	for file_path in (STUDENT_ACCOUNTS_FILE, PARENT_ACCOUNTS_FILE, ACCOUNTS_FILE):
		account_data = load_accounts(file_path)
		for account in account_data.get("accounts", []):
			if account.get("username") == username:
				return account, file_path
	return None, None


class AppRequestHandler(SimpleHTTPRequestHandler):
	def end_headers(self) -> None:
		self.send_header("X-Content-Type-Options", "nosniff")
		self.send_header("X-Frame-Options", "DENY")
		self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
		self.send_header(
			"Content-Security-Policy",
			"default-src 'self' 'unsafe-inline'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'",
		)
		super().end_headers()

	def _origin_is_allowed(self) -> bool:
		origin = self.headers.get("Origin", "").strip()
		if not origin:
			return True
		parsed_origin = urlsplit(origin)
		host = self.headers.get("Host", "").strip()
		return parsed_origin.scheme in {"http", "https"} and parsed_origin.netloc.casefold() == host.casefold()

	def _session_payload_from_cookie(self) -> dict | None:
		cookie = SimpleCookie()
		try:
			cookie.load(self.headers.get("Cookie", ""))
		except (TypeError, ValueError):
			return None
		morsel = cookie.get(SESSION_COOKIE_NAME)
		return read_session_payload(morsel.value) if morsel else None

	def _login_rate_key(self, username: str) -> tuple[str, str]:
		return self.client_address[0], username.strip().casefold()

	def _is_login_rate_limited(self, username: str) -> bool:
		key = self._login_rate_key(username)
		now = time.monotonic()
		with LOGIN_FAILURES_LOCK:
			attempts = [
				attempt for attempt in LOGIN_FAILURES.get(key, [])
				if now - attempt < LOGIN_ATTEMPT_WINDOW_SECONDS
			]
			if attempts:
				LOGIN_FAILURES[key] = attempts
			else:
				LOGIN_FAILURES.pop(key, None)
			return len(attempts) >= LOGIN_ATTEMPT_LIMIT

	def _record_login_failure(self, username: str) -> None:
		key = self._login_rate_key(username)
		now = time.monotonic()
		with LOGIN_FAILURES_LOCK:
			attempts = [
				attempt for attempt in LOGIN_FAILURES.get(key, [])
				if now - attempt < LOGIN_ATTEMPT_WINDOW_SECONDS
			]
			attempts.append(now)
			LOGIN_FAILURES[key] = attempts

	def _clear_login_failures(self, username: str) -> None:
		with LOGIN_FAILURES_LOCK:
			LOGIN_FAILURES.pop(self._login_rate_key(username), None)

	def _authenticated_account(self):
		payload = self._session_payload_from_cookie()
		username = str(payload.get("username", "")).strip() if payload else ""
		if not username:
			return None
		with ACCOUNT_LOCK:
			account, _ = find_account_by_username(username)
		return account if account and account.get("is_active", False) else None

	def _csrf_token_matches_session(self) -> bool:
		payload = self._session_payload_from_cookie()
		if not payload:
			return False
		provided = self.headers.get("X-CSRF-Token", "")
		expected = str(payload.get("csrf_token", ""))
		return bool(expected and provided and hmac.compare_digest(provided, expected))

	def _session_cookie(self, token: str, max_age: int) -> str:
		cookie = f"{SESSION_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
		forwarded_protocol = self.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower()
		if forwarded_protocol == "https" or os.environ.get("DONGHANH_COOKIE_SECURE", "").lower() == "true":
			cookie += "; Secure"
		return cookie

	def _prepare_public_static_path(self) -> bool:
		request = urlsplit(self.path)
		decoded_path = unquote(request.path).replace("\\", "/")
		normalized_path = posixpath.normpath("/" + decoded_path.lstrip("/"))
		if decoded_path.endswith("/") and normalized_path != "/":
			normalized_path += "/"
		if normalized_path == "/":
			normalized_path = "/Login/"
		canonical_path = PUBLIC_STATIC_PATHS.get(normalized_path.casefold())
		if canonical_path is None:
			self.send_error(404)
			return False
		self.path = canonical_path + (f"?{request.query}" if request.query else "")
		return True

	def _authorize_static_path(self) -> bool:
		request = urlsplit(self.path)
		path = request.path.casefold()
		required_role = None
		if path in {"/main/", "/main/index.html", "/chucnang/thong_tin_ca_nhan.html"}:
			required_role = "student"
		elif path == "/chucnangph.html":
			required_role = "parent"
		elif path == "/chucnang/thoi_khoa_bieu.html":
			query = dict(part.split("=", 1) for part in request.query.split("&") if "=" in part)
			required_role = "parent" if query.get("view", "").casefold() == "parent" else "student"
		if required_role is None:
			return True
		account = self._authenticated_account()
		if not account:
			self.send_response(302)
			self.send_header("Location", "/Login/")
			self.end_headers()
			return False
		role = str(account.get("role", "user")).casefold()
		allowed_roles = {"user", "student"} if required_role == "student" else {"parent"}
		if role not in allowed_roles:
			self.send_error(403)
			return False
		return True

	def do_GET(self) -> None:
		if urlsplit(self.path).path == "/api/session":
			account = self._authenticated_account()
			payload = self._session_payload_from_cookie()
			if not account or not payload:
				self.send_json(401, {"message": "Phiên đăng nhập không hợp lệ hoặc đã hết hạn."})
				return
			role = str(account.get("role", "user")).casefold()
			self.send_json(200, {
				"username": account.get("username", ""),
				"display_name": account.get("display_name", account.get("username", "")),
				"role": "parent" if role == "parent" else "student",
				"class_name": account.get("class_name", ""),
				"csrf_token": payload.get("csrf_token", ""),
			})
			return
		if not self._prepare_public_static_path():
			return
		if not self._authorize_static_path():
			return
		super().do_GET()

	def do_HEAD(self) -> None:
		if not self._prepare_public_static_path():
			return
		if not self._authorize_static_path():
			return
		super().do_HEAD()

	def send_json(self, status: int, payload: dict, headers: dict[str, str] | None = None) -> None:
		body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
		self.send_response(status)
		self.send_header("Content-Type", "application/json; charset=utf-8")
		self.send_header("Content-Length", str(len(body)))
		for name, value in (headers or {}).items():
			self.send_header(name, value)
		self.end_headers()
		self.wfile.write(body)

	def do_POST(self) -> None:
		request_path = urlsplit(self.path).path
		if request_path.startswith("/api/") and not self._origin_is_allowed():
			self.send_json(403, {"message": "Nguồn gửi yêu cầu không hợp lệ."})
			return
		try:
			length = int(self.headers.get("Content-Length", "0"))
		except ValueError:
			self.send_json(400, {"message": "Độ dài dữ liệu không hợp lệ."})
			return
		if length < 0:
			self.send_json(400, {"message": "Độ dài dữ liệu không hợp lệ."})
			return
		if length > MAX_REQUEST_BODY_BYTES:
			self.send_json(413, {"message": "Dữ liệu gửi lên vượt quá giới hạn cho phép."})
			return
		if request_path == "/api/logout":
			if length != 0:
				self.send_json(400, {"message": "Yêu cầu đăng xuất không được có body."})
				return
			if not self._csrf_token_matches_session():
				self.send_json(403, {"message": "CSRF token không hợp lệ."})
				return
			self.send_json(200, {"message": "Đã đăng xuất."}, {
				"Set-Cookie": self._session_cookie("", 0),
			})
			return
		if request_path not in ("/api/login", "/api/register"):
			self.send_error(404)
			return

		try:
			body = self.rfile.read(length)
			if len(body) != length:
				self.send_json(400, {"message": "Dữ liệu gửi lên không đầy đủ."})
				return
			data = json.loads(body.decode("utf-8"))
			if not isinstance(data, dict):
				self.send_json(400, {"message": "Dữ liệu gửi lên không hợp lệ."})
				return
		except (UnicodeDecodeError, ValueError):
			self.send_json(400, {"message": "Dữ liệu gửi lên không hợp lệ."})
			return

		username = str(data.get("username", "")).strip()
		password = str(data.get("password", ""))
		if not username or not password:
			self.send_json(400, {"message": "Vui lòng nhập tên đăng nhập và mật khẩu."})
			return

		if request_path == "/api/login":
			if self._is_login_rate_limited(username):
				self.send_json(429, {"message": "Bạn đã đăng nhập sai quá nhiều lần. Hãy thử lại sau 5 phút."})
				return
			try:
				with ACCOUNT_LOCK:
					account, account_file = find_account_by_username(username)
					if not account or not verify_password(account.get("password", ""), password) or not account.get("is_active", False):
						self._record_login_failure(username)
						self.send_json(401, {"message": "Tên đăng nhập hoặc mật khẩu không đúng."})
						return
					self._clear_login_failures(username)
					if not str(account.get("password", "")).startswith(PASSWORD_PREFIX):
						account_data = load_accounts(account_file)
						for stored_account in account_data["accounts"]:
							if stored_account.get("username") == account.get("username"):
								stored_account["password"] = hash_password(password)
								break
						save_accounts(account_data, account_file)
			except (OSError, RuntimeError):
				self.send_json(500, {"message": "Không thể đọc dữ liệu tài khoản."})
				return
			self.send_json(200, {
				"message": "Đăng nhập thành công.",
				"username": account["username"],
				"display_name": account.get("display_name", account["username"]),
				"role": account.get("role", "user")
			}, {"Set-Cookie": self._session_cookie(
				create_session_token(account["username"]), SESSION_TTL_SECONDS,
			)})
			return

		role = data.get("role", "student")
		if role not in ("student", "parent"):
			role = "student"
		target_file = get_account_file_for_role(role)
		try:
			with ACCOUNT_LOCK:
				if find_account_by_username(username)[0]:
					self.send_json(409, {"message": "Tên đăng nhập đã tồn tại."})
					return

				account_data = load_accounts(target_file)
				accounts = account_data.setdefault("accounts", [])
				accounts.append({
					"username": username,
					"password": hash_password(password),
					"display_name": str(data.get("display_name", username)).strip() or username,
					"role": "user" if role == "student" else "parent",
					"is_active": True
				})
				save_accounts(account_data, target_file)
		except (OSError, RuntimeError):
			self.send_json(500, {"message": "Không thể lưu dữ liệu tài khoản."})
			return
		self.send_json(201, {"message": "Tạo tài khoản thành công."})


def get_network_ip() -> str:
	with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
		try:
			connection.connect(("8.8.8.8", 80))
			return connection.getsockname()[0]
		except OSError:
			return "127.0.0.1"


class DongHanhHTTPServer(ThreadingHTTPServer):
	allow_reuse_address = False

	def server_bind(self) -> None:
		exclusive_address_use = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
		if exclusive_address_use is not None:
			self.socket.setsockopt(socket.SOL_SOCKET, exclusive_address_use, 1)
		super().server_bind()


def create_server(handler):
	for port in range(PORT, PORT + MAX_PORT_ATTEMPTS):
		try:
			return DongHanhHTTPServer((HOST, port), handler)
		except OSError:
			continue

	raise OSError(
		f"Khong the mo cong tu {PORT} den {PORT + MAX_PORT_ATTEMPTS - 1}."
	)


def main() -> None:
	"""Serve the web app and open the login page in the default browser."""
	handler = partial(AppRequestHandler, directory=str(PROJECT_DIR))
	server = create_server(handler)
	network_ip = get_network_ip()
	login_url = f"http://127.0.0.1:{server.server_port}/Login/"
	network_url = f"http://{network_ip}:{server.server_port}/Login/"

	print(f"Ung dung dang chay tai {login_url}")
	print(f"Mo tren thiet bi cung Wi-Fi: {network_url}")
	print("Nhan Ctrl+C de dung ung dung.")
	webbrowser.open(login_url)

	try:
		server.serve_forever()
	except KeyboardInterrupt:
		print("\nDa dung ung dung.")
	finally:
		server.server_close()


if __name__ == "__main__":
	main()

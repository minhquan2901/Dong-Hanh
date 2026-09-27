from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
from threading import RLock
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


def load_accounts(file_path: Path = ACCOUNTS_FILE) -> dict:
	_migrate_legacy_account_file(file_path)
	try:
		with file_path.open("r", encoding="utf-8") as file:
			data = json.load(file)
	except FileNotFoundError:
		return {"accounts": []}
	except json.JSONDecodeError as exc:
		raise RuntimeError(f"Tệp tài khoản bị lỗi JSON: {file_path}") from exc
	if not isinstance(data, dict) or not isinstance(data.get("accounts", []), list):
		raise RuntimeError(f"Cấu trúc tệp tài khoản không hợp lệ: {file_path}")
	return data


def save_accounts(data: dict, file_path: Path = ACCOUNTS_FILE) -> None:
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
	def do_GET(self) -> None:
		request_path = unquote(urlsplit(self.path).path).replace("\\", "/").lstrip("/").casefold()
		if request_path == "taikhoan" or request_path.startswith("taikhoan/"):
			self.send_error(404)
			return
		super().do_GET()

	def send_json(self, status: int, payload: dict) -> None:
		body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
		self.send_response(status)
		self.send_header("Content-Type", "application/json; charset=utf-8")
		self.send_header("Content-Length", str(len(body)))
		self.end_headers()
		self.wfile.write(body)

	def do_POST(self) -> None:
		if self.path not in ("/api/login", "/api/register"):
			self.send_error(404)
			return

		try:
			length = int(self.headers.get("Content-Length", "0"))
			data = json.loads(self.rfile.read(length).decode("utf-8"))
		except (ValueError, json.JSONDecodeError):
			self.send_json(400, {"message": "Dữ liệu gửi lên không hợp lệ."})
			return

		username = str(data.get("username", "")).strip()
		password = str(data.get("password", ""))
		if not username or not password:
			self.send_json(400, {"message": "Vui lòng nhập tên đăng nhập và mật khẩu."})
			return

		if self.path == "/api/login":
			try:
				account, _ = find_account_by_username(username)
			except (OSError, RuntimeError):
				self.send_json(500, {"message": "Không thể đọc dữ liệu tài khoản."})
				return
			if not account or account.get("password") != password or not account.get("is_active", False):
				self.send_json(401, {"message": "Tên đăng nhập hoặc mật khẩu không đúng."})
				return
			self.send_json(200, {
				"message": "Đăng nhập thành công.",
				"username": account["username"],
				"display_name": account.get("display_name", account["username"]),
				"role": account.get("role", "user")
			})
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
					"password": password,
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


def create_server(handler):
	for port in range(PORT, PORT + MAX_PORT_ATTEMPTS):
		try:
			return ThreadingHTTPServer((HOST, port), handler)
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

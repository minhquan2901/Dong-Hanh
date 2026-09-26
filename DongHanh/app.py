from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import webbrowser


PROJECT_DIR = Path(__file__).resolve().parent
HOST = "0.0.0.0"
PORT = 8000
MAX_PORT_ATTEMPTS = 10
ACCOUNTS_FILE = PROJECT_DIR / "TaiKhoan" / "accounts.json"
STUDENT_ACCOUNTS_FILE = PROJECT_DIR / "TaiKhoan" / "accounts2.json"
PARENT_ACCOUNTS_FILE = PROJECT_DIR / "TaiKhoan" / "accounts3.json"


def load_accounts(file_path: Path = ACCOUNTS_FILE) -> dict:
	try:
		with file_path.open("r", encoding="utf-8") as file:
			return json.load(file)
	except (OSError, json.JSONDecodeError):
		return {"accounts": []}


def save_accounts(data: dict, file_path: Path = ACCOUNTS_FILE) -> None:
	with file_path.open("w", encoding="utf-8") as file:
		json.dump(data, file, ensure_ascii=False, indent=2)


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
			account, _ = find_account_by_username(username)
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
		account_data = load_accounts(target_file)
		accounts = account_data.setdefault("accounts", [])
		if any(item.get("username") == username for item in accounts):
			self.send_json(409, {"message": "Tên đăng nhập đã tồn tại."})
			return

		accounts.append({
			"username": username,
			"password": password,
			"display_name": str(data.get("display_name", username)).strip() or username,
			"role": "user" if role == "student" else "parent",
			"is_active": True
		})
		save_accounts(account_data, target_file)
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

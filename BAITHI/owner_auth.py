from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from uuid import uuid4

from data_storage import backup_critical_file, data_file, write_json_atomic
from db import load_document


TOKEN_TTL_SECONDS = 8 * 60 * 60
ADMIN_ACCOUNTS_KEY = "admin_accounts"
DEFAULT_ADMIN_ACCOUNTS = [
    {
        "username": "gvLanAnh",
        "password_hash": "pbkdf2_sha256:310000:pae9o90hiYDxCM6CLIiGUw:CHdeqar4RmaNB9LT8Kk_ipz8bJlzAcKsZCwTAlAKqu4",
        "role": "owner",
        "is_active": True,
    },
    {
        "username": "Chithien_owner",
        "password_hash": "pbkdf2_sha256:310000:TnLGIGYheSIsqNaOaoIGfw:iVZoTt1dPBA35EXu7FoEfa1G3C37dy8wp0FskqkhB48",
        "role": "owner",
        "is_active": True,
    },
]


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _admin_accounts() -> list[dict[str, object]]:
    accounts = load_document(ADMIN_ACCOUNTS_KEY, DEFAULT_ADMIN_ACCOUNTS, "tài khoản admin")
    if not isinstance(accounts, list):
        return []
    return [account for account in accounts if isinstance(account, dict)]


def _find_admin(username: str) -> dict[str, object] | None:
    normalized = str(username or "").strip().casefold()
    return next(
        (
            account
            for account in _admin_accounts()
            if str(account.get("username", "")).strip().casefold() == normalized
            and account.get("is_active", True) is not False
        ),
        None,
    )


def _verify_admin_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded_hash.split(":", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
        actual = hashlib.pbkdf2_hmac(
            "sha256", str(password or "").encode("utf-8"), salt, int(iterations_text)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def authenticate_owner(username: str, password: str) -> bool:
    expected_username = os.environ.get("OWNER_USERNAME", "").strip()
    expected_password = os.environ.get("OWNER_PASSWORD", "")
    if not expected_username or len(expected_password) < 12:
        return False
    username_matches = hmac.compare_digest(
        str(username or "").strip().casefold(), expected_username.casefold()
    )
    password_matches = hmac.compare_digest(str(password or ""), expected_password)
    if username_matches and password_matches:
        return True
    admin = _find_admin(username)
    return bool(admin and _verify_admin_password(password, str(admin.get("password_hash", ""))))


def owner_configuration_error() -> str | None:
    if not os.environ.get("OWNER_USERNAME", "").strip():
        return "Chưa cấu hình OWNER_USERNAME trong Render Environment."
    if len(os.environ.get("OWNER_PASSWORD", "")) < 12:
        return "OWNER_PASSWORD chưa được cấu hình hoặc ngắn hơn 12 ký tự."
    try:
        _get_user_session_secret()
    except (OSError, RuntimeError):
        return "STUDYSYNC_SESSION_SECRET chưa hợp lệ hoặc chưa cấu hình persistent storage."
    return None


def _get_user_session_secret() -> str:
    configured_secret = os.environ.get("STUDYSYNC_SESSION_SECRET", "")
    if configured_secret:
        if len(configured_secret) < 32:
            raise RuntimeError("STUDYSYNC_SESSION_SECRET phải có ít nhất 32 ký tự.")
        return configured_secret
    owner_secret = os.environ.get("OWNER_SESSION_SECRET", "")
    if len(owner_secret) >= 32:
        return owner_secret

    secret_file = data_file("session_signing_secret.json")
    if secret_file.exists():
        try:
            secret = json.loads(secret_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Không đọc được khóa phiên đăng nhập.") from exc
        if isinstance(secret, str) and len(secret) >= 32:
            return secret
        raise RuntimeError("Khóa phiên đăng nhập không hợp lệ.")

    secret = uuid4().hex + uuid4().hex
    backup_critical_file("session_signing_secret.json")
    write_json_atomic(secret_file, secret)
    return secret


def create_user_token(username: str, role: str, session_version: int = 0) -> str:
    secret = _get_user_session_secret()
    payload = _b64encode(json.dumps({
        "sub": username,
        "role": role,
        "ver": session_version,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return f"{payload}.{_b64encode(signature)}"


def verify_user_token(token: str, username: str, role: str | None = None, session_version: int = 0) -> bool:
    try:
        secret = _get_user_session_secret()
        payload_part, signature_part = str(token or "").split(".", 1)
        supplied_signature = _b64decode(signature_part)
        expected_signature = hmac.new(
            secret.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return False
        payload = json.loads(_b64decode(payload_part).decode("utf-8"))
        return (
            str(payload.get("sub", "")).strip().lower() == str(username or "").strip().lower()
            and (role is None or payload.get("role") == role)
            and int(payload.get("ver", 0)) == session_version
            and int(payload.get("exp", 0)) > int(time.time())
        )
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def create_owner_token(username: str | None = None) -> str:
    secret = _get_user_session_secret()
    if len(secret) < 32:
        raise RuntimeError("STUDYSYNC_SESSION_SECRET phải có ít nhất 32 ký tự.")
    payload = _b64encode(json.dumps({
        "sub": str(username or os.environ.get("OWNER_USERNAME", "")).strip(),
        "role": "owner",
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return f"{payload}.{_b64encode(signature)}"


def verify_owner_token(token: str) -> bool:
    try:
        secret = _get_user_session_secret()
    except (OSError, RuntimeError):
        return False
    if len(secret) < 32:
        return False
    try:
        payload_part, signature_part = str(token or "").split(".", 1)
        supplied_signature = _b64decode(signature_part)
        expected_signature = hmac.new(
            secret.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return False
        payload = json.loads(_b64decode(payload_part).decode("utf-8"))
        username = str(payload.get("sub", "")).strip()
        configured_owner = os.environ.get("OWNER_USERNAME", "").strip()
        valid_identity = (
            bool(configured_owner)
            and username.casefold() == configured_owner.casefold()
        ) or _find_admin(username) is not None
        return payload.get("role") == "owner" and valid_identity and int(payload.get("exp", 0)) > int(time.time())
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return False

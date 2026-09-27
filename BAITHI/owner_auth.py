from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from uuid import uuid4

from data_storage import data_file, write_json_atomic


TOKEN_TTL_SECONDS = 8 * 60 * 60


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def authenticate_owner(username: str, password: str) -> bool:
    expected_username = os.environ.get("OWNER_USERNAME", "").strip()
    expected_password = os.environ.get("OWNER_PASSWORD", "")
    if not expected_username or len(expected_password) < 12:
        return False
    return hmac.compare_digest(str(username or "").strip(), expected_username) and hmac.compare_digest(
        str(password or ""), expected_password
    )


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
    write_json_atomic(secret_file, secret)
    return secret


def create_user_token(username: str, role: str) -> str:
    secret = _get_user_session_secret()
    payload = _b64encode(json.dumps({
        "sub": username,
        "role": role,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return f"{payload}.{_b64encode(signature)}"


def verify_user_token(token: str, username: str, role: str | None = None) -> bool:
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
            and int(payload.get("exp", 0)) > int(time.time())
        )
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def create_owner_token() -> str:
    secret = _get_user_session_secret()
    if len(secret) < 32:
        raise RuntimeError("STUDYSYNC_SESSION_SECRET phải có ít nhất 32 ký tự.")
    payload = _b64encode(json.dumps({
        "sub": os.environ.get("OWNER_USERNAME", "").strip(),
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
        return (
            payload.get("role") == "owner"
            and payload.get("sub") == os.environ.get("OWNER_USERNAME", "").strip()
            and int(payload.get("exp", 0)) > int(time.time())
        )
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return False

"""Chuyển mật khẩu đang lưu bản rõ sang dạng hash trên Neon.

Chạy MỘT LẦN DUY NHẤT sau khi đã triển khai bản có hash_password:

    $env:STUDYSYNC_DATABASE_URL = "postgresql://..."
    .\.venv\Scripts\python.exe migrate_passwords.py

Script chỉ đổi mật khẩu còn là bản rõ. Tài khoản nào đã hash rồi thì giữ
nguyên. Người dùng không phải đổi mật khẩu sau khi chạy script này.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from auth_service import hash_password, is_hashed_password, load_users, save_users


def main() -> int:
    users = load_users()
    pending = [u for u in users if not is_hashed_password(u.get("password", ""))]

    print(f"Tong so tai khoan      : {len(users)}")
    print(f"Chua hash (sua duoc)    : {len(pending)}")
    print(f"Da hash roi             : {len(users) - len(pending)}")

    if not pending:
        print("\nKhong con mat khau ban ro. Khong can lam gi.")
        return 0

    print("\nTai khoan se duoc chuyen:")
    for user in pending:
        print(f"  - {user['username']}")

    print("\nDang hash...")
    changed = 0
    for user in pending:
        user["password"] = hash_password(user["password"])
        changed += 1
    save_users(users)

    # Doc lai de chung minh da hash thuc su.
    after = load_users()
    still_plain = [u["username"] for u in after if not is_hashed_password(u.get("password", ""))]

    print(f"\nDa hash               : {changed} tai khoan")
    print(f"Con ban ro sau migrate: {still_plain or '(khong con)'}")
    if still_plain:
        print("Migrate khong hoan tat, hay chay lai.")
        return 1
    print("\nXong. Moi tai khoan van giu nguyen mat khau cu, khong can doi gi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

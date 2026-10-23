"""平台账户的读写。"""
from __future__ import annotations

import re
import secrets
import time

from ..db import Db
from ..security.passwords import hash_password, verify_password

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5-]{2,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _key(value: str) -> str:
    return value.strip().lower()


def find_by_login(db: Db, identifier: str):
    text = identifier.strip()
    if not text:
        return None
    row = db.query_one("SELECT * FROM users WHERE username_key = ?", (_key(text),))
    if row:
        return row
    if "@" in text:
        return db.query_one("SELECT * FROM users WHERE email_key = ?", (_key(text),))
    return None


def get(db: Db, user_id: str):
    return db.query_one("SELECT * FROM users WHERE id = ?", (user_id,))


def create(db: Db, username: str, password: str | None,
           email: str | None = None, *, status: str = "active") -> tuple[str | None, str]:
    """返回 (user_id, error)。"""
    username = username.strip()
    if not USERNAME_RE.match(username):
        return None, "用户名需为 2–32 位，可用字母、数字、下划线、连字符或中文"
    if password is not None and len(password) < 8:
        return None, "密码至少 8 位"
    if email:
        email = email.strip()
        if not EMAIL_RE.match(email):
            return None, "邮箱格式不正确"

    if db.query_one("SELECT 1 FROM users WHERE username_key = ?", (_key(username),)):
        return None, "该用户名已被占用"
    if email and db.query_one("SELECT 1 FROM users WHERE email_key = ?", (_key(email),)):
        return None, "该邮箱已被使用"

    user_id = secrets.token_hex(16)
    now = time.time()
    try:
        db.execute(
            "INSERT INTO users (id, username, username_key, email, email_key,"
            " password_hash, display_name, status, token_version, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, username, _key(username), email or None,
             _key(email) if email else None,
             hash_password(password) if password else None,
             username, status, 0, now, now),
        )
    except Exception:  # noqa: BLE001 - 唯一约束竞争
        return None, "该用户名或邮箱已被占用"
    return user_id, ""


def activate(db: Db, user_id: str) -> bool:
    return db.execute(
        "UPDATE users SET status = 'active', updated_at = ? WHERE id = ? AND status = 'pending'",
        (time.time(), user_id),
    ) > 0


def create_with_id(db: Db, user_id: str, username: str,
                   email: str | None = None) -> str:
    """用预先确定的 id 建号（供"先绑定再落库"的原子顺序使用）。

    返回错误信息，空串表示成功。password_hash 为 NULL：
    该账号只能通过 TFV5 登录，用户可稍后在账户页设置平台密码。
    """
    username = username.strip()
    if not USERNAME_RE.match(username):
        return "用户名需为 2–32 位，可用字母、数字、下划线、连字符或中文"
    if db.query_one("SELECT 1 FROM users WHERE username_key = ?", (_key(username),)):
        return "该用户名已被占用"
    if email and db.query_one("SELECT 1 FROM users WHERE email_key = ?", (_key(email),)):
        email = None  # 邮箱冲突不阻塞建号，降级为不写邮箱

    now = time.time()
    try:
        db.execute(
            "INSERT INTO users (id, username, username_key, email, email_key,"
            " password_hash, display_name, status, token_version, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, username, _key(username), email or None,
             _key(email) if email else None, None, username, "active", 0, now, now),
        )
    except Exception:  # noqa: BLE001
        return "建号失败，请重试"
    return ""


def unique_username(db: Db, preferred: str) -> str:
    """给"用 TFV5 凭据首次登录"的自动建号用：冲突就加后缀。"""
    base = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fa5-]", "_", preferred.strip())[:24] or "tf_user"
    if len(base) < 2:
        base = f"{base}_u"
    candidate = base
    for index in range(1, 50):
        if not db.query_one("SELECT 1 FROM users WHERE username_key = ?", (_key(candidate),)):
            return candidate
        suffix = f"_{index}"
        candidate = base[: max(2, 32 - len(suffix))] + suffix
    return f"tf_{secrets.token_hex(4)}"


def verify_login(db: Db, identifier: str, password: str):
    row = find_by_login(db, identifier)
    if row is None:
        # 与"密码错"同构，避免账号枚举
        verify_password(None, password)
        return None, "auth_failed"
    if row["status"] == "suspended":
        return None, "account_suspended"
    if not verify_password(row["password_hash"], password):
        return None, "auth_failed"
    # pending（待邮箱验证）允许通过凭据校验，由调用方给出专门的提示与重发入口
    return row, ""


def set_password(db: Db, user_id: str, password: str) -> None:
    db.execute(
        "UPDATE users SET password_hash = ?, updated_at = ?, token_version = token_version + 1"
        " WHERE id = ?",
        (hash_password(password), time.time(), user_id),
    )


def public_view(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "email": row["email"],
        "has_password": bool(row["password_hash"]),
        "role": row["role"] or "user",
        "status": row["status"],
        "created_at": row["created_at"],
    }


def set_role(db: Db, user_id: str, role: str) -> bool:
    if role not in ("user", "admin"):
        return False
    return db.execute(
        "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
        (role, time.time(), user_id),
    ) > 0


def set_status(db: Db, user_id: str, status: str) -> bool:
    if status not in ("active", "suspended"):
        return False
    ok = db.execute(
        "UPDATE users SET status = ?, updated_at = ?, token_version = token_version + 1"
        " WHERE id = ?",
        (status, time.time(), user_id),
    ) > 0
    return ok


def list_users(db: Db, limit: int = 200) -> list[dict]:
    rows = db.query(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    return [public_view(row) for row in rows]


def count_admins(db: Db) -> int:
    row = db.query_one("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'")
    return int(row["n"]) if row else 0

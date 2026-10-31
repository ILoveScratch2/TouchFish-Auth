"""
平台浏览器会话与 CSRF

不使用 JWT 因为支持即时撤销
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any

from ..db import Db

SESSION_COOKIE = "tf_session"
CSRF_COOKIE = "tf_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Db, user_id: str, ttl: int,
                   ip: str | None = None, user_agent: str | None = None) -> tuple[str, str]:
    """返回 (session_id, csrf_token)。库里只存 session 的 sha256。"""
    sid = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    now = time.time()
    db.execute(
        "INSERT INTO sessions (id, user_id, created_at, last_seen_at, expires_at, ip, user_agent)"
        " VALUES (?,?,?,?,?,?,?)",
        (_hash(sid), user_id, now, now, now + ttl, ip, (user_agent or "")[:256]),
    )
    return sid, csrf


def resolve_session(db: Db, sid: str | None) -> dict[str, Any] | None:
    if not sid:
        return None
    row = db.query_one(
        "SELECT s.id, s.user_id, s.expires_at, s.revoked_at, u.username, u.display_name,"
        " u.email, u.status, u.password_hash, u.role"
        " FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = ?",
        (_hash(sid),),
    )
    if row is None:
        return None
    if row["revoked_at"] is not None:
        return None
    if float(row["expires_at"]) < time.time():
        return None
    if row["status"] != "active":
        return None
    return {
        "session_id": row["id"],
        "user_id": row["user_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "email": row["email"],
        "has_password": bool(row["password_hash"]),
        "role": row["role"] or "user",
    }


def touch_session(db: Db, session_id: str) -> None:
    db.execute("UPDATE sessions SET last_seen_at = ? WHERE id = ?", (time.time(), session_id))


def revoke_session(db: Db, session_id: str, user_id: str) -> bool:
    return db.execute(
        "UPDATE sessions SET revoked_at = ? WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
        (time.time(), session_id, user_id),
    ) > 0


def revoke_all_except(db: Db, user_id: str, keep: str | None) -> int:
    now = time.time()
    if keep:
        return db.execute(
            "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND id != ? AND revoked_at IS NULL",
            (now, user_id, keep),
        )
    return db.execute(
        "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
        (now, user_id),
    )


def list_sessions(db: Db, user_id: str) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT id, created_at, last_seen_at, expires_at, ip, user_agent FROM sessions"
        " WHERE user_id = ? AND revoked_at IS NULL AND expires_at > ? ORDER BY created_at DESC",
        (user_id, time.time()),
    )
    return [
        {
            "id": row["id"],
            "created_at": row["created_at"],
            "last_seen_at": row["last_seen_at"],
            "expires_at": row["expires_at"],
            "ip": row["ip"],
            "user_agent": row["user_agent"],
        }
        for row in rows
    ]


def find_session_row(db: Db, sid: str) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM sessions WHERE id = ?", (_hash(sid),))
    return dict(row) if row else None

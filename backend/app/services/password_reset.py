"""密码重置码

"""
from __future__ import annotations

import hashlib
import secrets
import time

from ..db import Db

TTL_SECONDS = 900
MAX_ATTEMPTS = 5
COOLDOWN_SECONDS = 60


def _hash(code: str, row_id: str) -> str:
    return hashlib.sha256(f"{row_id}:{code}".encode("utf-8")).hexdigest()


def _key(email: str) -> str:
    return email.strip().lower()


def cooling_down(db: Db, user_id: str) -> int:
    """返回还需等待的秒数；0 表示可以发信"""
    row = db.query_one(
        "SELECT created_at FROM password_resets WHERE user_id = ?"
        " ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    if row is None:
        return 0
    remain = COOLDOWN_SECONDS - (time.time() - float(row["created_at"]))
    return max(0, int(remain))


def issue(db: Db, user_id: str, email: str) -> tuple[str, str]:
    """作废旧码并生成新码，返回 (row_id, code)"""
    db.execute(
        "UPDATE password_resets SET consumed_at = ? WHERE user_id = ? AND consumed_at IS NULL",
        (time.time(), user_id),
    )
    row_id = secrets.token_hex(12)
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = time.time()
    db.execute(
        "INSERT INTO password_resets (id, user_id, email, email_key, code_hash,"
        " created_at, expires_at) VALUES (?,?,?,?,?,?,?)",
        (row_id, user_id, email, _key(email), _hash(code, row_id), now,
         now + TTL_SECONDS),
    )
    return row_id, code


def verify_by_email(db: Db, email: str, code: str) -> str | None:
    """按邮箱校验，成功返回 user_id
    """
    row = db.query_one(
        "SELECT * FROM password_resets WHERE email_key = ? AND consumed_at IS NULL"
        " ORDER BY created_at DESC LIMIT 1",
        (_key(email),),
    )
    if row is None:
        return None
    return row["user_id"] if _consume(db, row, code) else None


def _consume(db: Db, row, code: str) -> bool:
    if float(row["expires_at"]) < time.time():
        return False
    if int(row["attempts"]) >= MAX_ATTEMPTS:
        return False
    if secrets.compare_digest(row["code_hash"], _hash(code.strip(), row["id"])):
        db.execute("UPDATE password_resets SET consumed_at = ? WHERE id = ?",
                   (time.time(), row["id"]))
        return True
    db.execute("UPDATE password_resets SET attempts = attempts + 1 WHERE id = ?",
               (row["id"],))
    return False

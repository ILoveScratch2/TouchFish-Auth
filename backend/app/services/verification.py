"""邮箱验证码。库里只存哈希，明文只在发信时存在于内存。"""
from __future__ import annotations

import hashlib
import secrets
import time

from ..db import Db

TTL_SECONDS = 900
MAX_ATTEMPTS = 5


def _hash(code: str, row_id: str) -> str:
    return hashlib.sha256(f"{row_id}:{code}".encode("utf-8")).hexdigest()


def issue(db: Db, user_id: str, email: str) -> tuple[str, str]:
    """生成新验证码，返回 (row_id, code)。旧码立即作废。"""
    db.execute(
        "UPDATE email_verifications SET consumed_at = ? WHERE user_id = ? AND consumed_at IS NULL",
        (time.time(), user_id),
    )
    row_id = secrets.token_hex(12)
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = time.time()
    db.execute(
        "INSERT INTO email_verifications (id, user_id, email, code_hash, created_at, expires_at)"
        " VALUES (?,?,?,?,?,?)",
        (row_id, user_id, email, _hash(code, row_id), now, now + TTL_SECONDS),
    )
    return row_id, code


def verify(db: Db, user_id: str, code: str) -> bool:
    row = db.query_one(
        "SELECT * FROM email_verifications WHERE user_id = ? AND consumed_at IS NULL"
        " ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    if row is None:
        return False
    return _consume(db, row, code)


def verify_by_id(db: Db, verification_id: str, code: str) -> str | None:
    """按验证码记录 id 校验，成功返回 user_id。

    用 id 当句柄避免"只凭邮箱就能爆破验证码"：id 是 24 位随机串，
    只有注册/重发接口的响应里才会拿到。
    """
    row = db.query_one("SELECT * FROM email_verifications WHERE id = ?", (verification_id,))
    if row is None or row["consumed_at"] is not None:
        return None
    return row["user_id"] if _consume(db, row, code) else None


def _consume(db: Db, row, code: str) -> bool:
    if float(row["expires_at"]) < time.time():
        return False
    if int(row["attempts"]) >= MAX_ATTEMPTS:
        return False
    if secrets.compare_digest(row["code_hash"], _hash(code.strip(), row["id"])):
        db.execute("UPDATE email_verifications SET consumed_at = ? WHERE id = ?",
                   (time.time(), row["id"]))
        return True
    db.execute("UPDATE email_verifications SET attempts = attempts + 1 WHERE id = ?",
               (row["id"],))
    return False


def pending_email(db: Db, user_id: str) -> str | None:
    row = db.query_one(
        "SELECT email FROM email_verifications WHERE user_id = ? AND consumed_at IS NULL"
        " ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    return row["email"] if row else None

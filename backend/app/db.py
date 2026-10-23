"""SQLite 访问层。

FastAPI 的同步端点跑在线程池里，这里用一个全局连接 + 可重入锁保证线程安全。

ORM 没玩过不会玩
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL,
    username_key  TEXT NOT NULL UNIQUE,   -- lower(username)，模拟 COLLATE NOCASE
    email         TEXT,
    email_key     TEXT UNIQUE,
    password_hash TEXT,                   -- NULL = 仅第三方/仅 TFV5 登录
    display_name  TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    role          TEXT NOT NULL DEFAULT 'user',   -- user / admin
    token_version INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    created_at   REAL NOT NULL,
    last_seen_at REAL,
    expires_at   REAL NOT NULL,
    revoked_at   REAL,
    ip           TEXT,
    user_agent   TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS tfv5_instances (
    id                  TEXT PRIMARY KEY,
    base_url            TEXT NOT NULL,
    display_name        TEXT NOT NULL,
    issuer              TEXT NOT NULL,
    audience            TEXT,
    allow_insecure_http INTEGER NOT NULL DEFAULT 0,
    is_default          INTEGER NOT NULL DEFAULT 0,
    created_at          REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS connections (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    instance_id       TEXT NOT NULL,
    tfv5_uid          INTEGER NOT NULL,
    tfv5_username     TEXT NOT NULL,
    iss               TEXT NOT NULL,
    sub               TEXT NOT NULL,
    refresh_token_enc BLOB,
    bind_channel      TEXT NOT NULL DEFAULT 'platform',
    bound_at          REAL NOT NULL,
    last_login_at     REAL,
    UNIQUE (user_id, instance_id),
    UNIQUE (instance_id, tfv5_uid)
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket      TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    client_id   TEXT NOT NULL,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    consumed_at REAL
);

CREATE TABLE IF NOT EXISTS oauth_accounts (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    provider          TEXT NOT NULL,
    provider_uid      TEXT NOT NULL,
    email             TEXT,
    login             TEXT,
    avatar_url        TEXT,
    access_token_enc  BLOB,
    linked_at         REAL NOT NULL,
    UNIQUE (provider, provider_uid),
    UNIQUE (user_id, provider)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         TEXT PRIMARY KEY,
    at         REAL NOT NULL,
    user_id    TEXT,
    event      TEXT NOT NULL,
    ip         TEXT,
    user_agent TEXT,
    detail     TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);

-- 站点配置（管理员可改，键值对；敏感值单独存，读取时不回显）
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    is_secret  INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    updated_by TEXT
);

-- 邮箱验证码（只存 sha256(code + salt)）
CREATE TABLE IF NOT EXISTS email_verifications (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    email      TEXT NOT NULL,
    code_hash  TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    consumed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_verify_user ON email_verifications(user_id);
"""


class Db:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, timeout=15)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """给既有库补列。SQLite 没有 IF NOT EXISTS 加列，只能先看 PRAGMA。"""
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(users)")}
        if "role" not in columns:
            self._conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.rowcount

    def execute_many(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def prune(self) -> dict[str, int]:
        """回收过期数据。这些表原先只增不删，长期运行会无限膨胀。

        保留策略：
          - tickets：过期即删（一次性凭据，过期后无任何用途）
          - email_verifications：过期后保留 1 天便于排查，之后删
          - sessions：过期后保留 7 天（供"登录设备"页展示历史）；
            **不区分是否显式吊销** —— 自然过期而不登出的会话同样要回收，
            否则它们会永久堆积
          - audit_log：保留 180 天
        """
        now = time.time()
        day = 86400.0
        removed = {
            "tickets": self.execute(
                "DELETE FROM tickets WHERE expires_at < ?", (now - day,)),
            "email_verifications": self.execute(
                "DELETE FROM email_verifications WHERE expires_at < ?", (now - day,)),
            "sessions": self.execute(
                "DELETE FROM sessions WHERE expires_at < ?", (now - 7 * day,)),
            "audit_log": self.execute(
                "DELETE FROM audit_log WHERE at < ?", (now - 180 * day,)),
        }
        return removed

    def audit(self, event: str, user_id: str | None = None,
              ip: str | None = None, user_agent: str | None = None,
              detail: str | None = None) -> None:
        """审计。调用方负责不要把密码写进 detail。"""
        import secrets as _secrets
        self.execute(
            "INSERT INTO audit_log (id, at, user_id, event, ip, user_agent, detail)"
            " VALUES (?,?,?,?,?,?,?)",
            (_secrets.token_hex(12), time.time(), user_id, event, ip, user_agent, detail),
        )

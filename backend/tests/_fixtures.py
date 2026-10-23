"""测试共用夹具：站点配置的整表快照 / 还原。

为什么需要：这些 HTTP 冒烟要注册账号。如果站点当前开着
「注册/登录需要人机验证」或「必须验证邮箱」，它们根本拿不到会话，
后面会连锁失败——看起来像代码坏了，其实是被测试环境的配置挡住。

做法：测试前整表清空（回到默认值），测试后整表还原。
磁盘上另留一份 JSON 备份，万一进程被强杀可以手工救回。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BACKEND = Path(__file__).resolve().parent.parent
DB_PATH = BACKEND / "data" / "auth.db"
BACKUP_PATH = BACKEND / "data" / "settings_snapshot.json"


def _connect() -> sqlite3.Connection | None:
    if not DB_PATH.is_file():
        return None
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def snapshot_settings() -> list[dict]:
    conn = _connect()
    if conn is None:
        return []
    try:
        return [dict(row) for row in conn.execute("SELECT * FROM settings")]
    finally:
        conn.close()


def restore_settings(rows: list[dict]) -> None:
    conn = _connect()
    if conn is None:
        return
    try:
        conn.execute("DELETE FROM settings")
        for row in rows:
            conn.execute(
                "INSERT INTO settings (key, value, is_secret, updated_at, updated_by)"
                " VALUES (?,?,?,?,?)",
                (row["key"], row["value"], row["is_secret"],
                 row["updated_at"], row["updated_by"]),
            )
        conn.commit()
    finally:
        conn.close()


def wipe_settings() -> None:
    """清空配置 → 全部回到默认值（验证码关、邮箱验证关）。"""
    conn = _connect()
    if conn is None:
        return
    try:
        conn.execute("DELETE FROM settings")
        conn.commit()
    finally:
        conn.close()


@contextmanager
def relaxed_site_settings() -> Iterator[None]:
    """让测试跑在默认配置下，结束后原样还原。"""
    original = snapshot_settings()
    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_PATH.write_text(
        json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    wipe_settings()
    try:
        yield
    finally:
        restore_settings(original)
        try:
            BACKUP_PATH.unlink()
        except OSError:
            pass

"""TFV5 实例仓库。

多实例（主站 + 测试服），但默认一个
"""
from __future__ import annotations

import time
from urllib.parse import urlparse

from ..db import Db
from ..settings import Settings
from .tfv5 import Instance


def _normalize(url: str) -> str:
    parsed = urlparse(url.strip().rstrip("/"))
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return f"{host}:{port}"


def seed_default(db: Db, settings: Settings) -> None:
    if not settings.default_instance_url:
        return
    existing = db.query_one("SELECT id FROM tfv5_instances WHERE is_default = 1")
    if existing:
        return
    db.execute(
        "INSERT OR REPLACE INTO tfv5_instances"
        " (id, base_url, display_name, issuer, audience, allow_insecure_http, is_default, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (
            settings.default_instance_id,
            settings.default_instance_url.rstrip("/"),
            "TouchFish",
            settings.issuer,
            None,
            1 if settings.tfv5_allow_insecure_http else 0,
            1,
            time.time(),
        ),
    )


def _row_to_instance(row) -> Instance:
    return Instance(
        id=row["id"],
        base_url=row["base_url"],
        display_name=row["display_name"],
        issuer=row["issuer"],
        audience=row["audience"],
        allow_insecure_http=bool(row["allow_insecure_http"]),
    )


def list_instances(db: Db) -> list[Instance]:
    rows = db.query("SELECT * FROM tfv5_instances ORDER BY is_default DESC, created_at")
    return [_row_to_instance(row) for row in rows]


def get_instance(db: Db, instance_id: str | None) -> Instance | None:
    if instance_id:
        row = db.query_one("SELECT * FROM tfv5_instances WHERE id = ?", (instance_id,))
        if row:
            return _row_to_instance(row)
    row = db.query_one("SELECT * FROM tfv5_instances WHERE is_default = 1")
    if row:
        return _row_to_instance(row)
    row = db.query_one("SELECT * FROM tfv5_instances ORDER BY created_at LIMIT 1")
    return _row_to_instance(row) if row else None


def resolve_target(db: Db, target: str | None) -> Instance | None:
    """按客户端传来的 TFV5 地址找实例"""
    if target:
        wanted = _normalize(target)
        for instance in list_instances(db):
            if _normalize(instance.base_url) == wanted:
                return instance
    return get_instance(db, None)


def detail(db: Db, instance: Instance) -> dict:
    return {
        "id": instance.id,
        "base_url": instance.base_url,
        "display_name": instance.display_name,
        "issuer": instance.issuer,
        "audience": instance.audience,
    }


def upsert(db: Db, settings, *, instance_id: str, base_url: str,
           display_name: str, audience: str | None) -> Instance:
    """新增或更新实例。issuer 始终跟随平台自身的 issuer"""
    base = base_url.strip().rstrip("/")
    if not (base.startswith("http://") or base.startswith("https://")):
        raise ValueError("base_url 必须是 http(s)")
    existing = db.query_one("SELECT id FROM tfv5_instances WHERE id = ?", (instance_id,))
    if existing:
        db.execute(
            "UPDATE tfv5_instances SET base_url = ?, display_name = ?, audience = ?,"
            " issuer = ?, allow_insecure_http = ? WHERE id = ?",
            (base, display_name, audience, settings.issuer,
             1 if base.startswith("http://") else 0, instance_id),
        )
    else:
        db.execute(
            "INSERT INTO tfv5_instances (id, base_url, display_name, issuer, audience,"
            " allow_insecure_http, is_default, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (instance_id, base, display_name, settings.issuer, audience,
             1 if base.startswith("http://") else 0,
             0 if db.query_one("SELECT 1 FROM tfv5_instances") else 1,
             time.time()),
        )
    instance = get_instance(db, instance_id)
    assert instance is not None
    return instance


def delete(db: Db, instance_id: str) -> tuple[bool, str]:
    """删除实例"""
    used = db.query_one("SELECT COUNT(*) AS n FROM connections WHERE instance_id = ?",
                        (instance_id,))
    if used and int(used["n"]) > 0:
        return False, f"仍有 {int(used['n'])} 个账户绑定在该实例上，请先解除绑定"
    total = db.query_one("SELECT COUNT(*) AS n FROM tfv5_instances")
    if total and int(total["n"]) <= 1:
        return False, "至少需要保留一个实例"
    removed = db.execute("DELETE FROM tfv5_instances WHERE id = ?", (instance_id,))
    return (removed > 0), "" if removed else "实例不存在"

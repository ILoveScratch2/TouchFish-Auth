"""进程级运行时容器。"""
from __future__ import annotations

from dataclasses import dataclass

from .db import Db
from .security.signer import KeyStore
from .services import oauth
from .settings import Settings


@dataclass
class Runtime:
    settings: Settings
    db: Db
    keystore: KeyStore


_runtime: Runtime | None = None


def init(settings: Settings, db: Db, keystore: KeyStore) -> Runtime:
    global _runtime
    _runtime = Runtime(settings=settings, db=db, keystore=keystore)
    # github test legacy
    # of course u dont need this
    oauth.migrate_legacy(db, settings)
    return _runtime


def get() -> Runtime:
    if _runtime is None:  # pragma: no cover
        raise RuntimeError("运行时未初始化")
    return _runtime

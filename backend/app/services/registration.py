"""注册策略"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from ..db import Db
from ..settings import Settings
from . import site
from .tfv5 import Instance, Tfv5Error, get_client

INFO_TTL = 60.0            # 探测成功 TTL
INFO_RETRY_INTERVAL = 15.0
INFO_STALE_GRACE = 300.0   # 刷新失败时最多沿用
PROBE_TIMEOUT = 5.0

log = logging.getLogger("touchfish-auth.registration")


@dataclass
class _Entry:
    info: dict | None = None   # 最近一次成功 /info
    good_at: float = 0.0       # info 时间
    attempt_at: float = 0.0    # 最近一次访问（）


_cache: dict[str, _Entry] = {}
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _cache_key(instance: Instance) -> str:
    # 同一个 id 换了地址也要换
    return f"{instance.id}|{instance.base_url}"


def _lock_for(key: str) -> threading.Lock:
    with _guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.Lock()
        return lock


def _cached(key: str) -> _Entry | None:
    with _guard:
        return _cache.get(key)


def _probe(instance: Instance) -> dict | None:
    """GET info"""
    try:
        return get_client().info(instance, timeout=PROBE_TIMEOUT)
    except Tfv5Error:
        return None


def tfv5_info(instance: Instance) -> dict | None:
    key = _cache_key(instance)
    now = time.time()
    entry = _cached(key)

    # 刚刚检测
    if entry is not None and now - entry.attempt_at < INFO_RETRY_INTERVAL:
        return entry.info
    if entry is not None and entry.info is not None and now - entry.good_at < INFO_TTL:
        return entry.info

    lock = _lock_for(key)
    if not lock.acquire(blocking=False):
        # 已有请求在探测
        if entry is not None:
            return entry.info
        with lock:
            fresh = _cached(key)
        return fresh.info if fresh else None

    try:
        # 别人可能探过
        entry = _cached(key)
        now = time.time()
        if entry is not None and now - entry.attempt_at < INFO_RETRY_INTERVAL:
            return entry.info

        info = _probe(instance)
        with _guard:
            if entry is None:
                entry = _cache.setdefault(key, _Entry())
            entry.attempt_at = time.time()
            if info is not None:
                entry.info = info
                entry.good_at = entry.attempt_at
                return info
            stale_for = entry.attempt_at - entry.good_at if entry.info is not None else 0.0

        if entry.info is not None and stale_for < INFO_TTL + INFO_STALE_GRACE:
            log.warning(
                "TFV5 /info 探测失败，沿用 %.0f 秒前的缓存（实例 %s，策略可能已变更）",
                stale_for, instance.id,
            )
            return entry.info
        return None
    finally:
        lock.release()


def clear_cache() -> None:
    """测试 / 维护用"""
    with _guard:
        _cache.clear()


def mode(db: Db, settings: Settings) -> str:
    return str(site.get_value(db, settings, "registration_mode") or settings.allow_registration)


def registration_allowed(db: Db, settings: Settings,
                         instance: Instance | None) -> tuple[bool, str]:
    current = mode(db, settings)
    if current == "force_off":
        return False, "管理员已关闭注册"
    if current == "force_on":
        return True, ""
    if instance is None:
        return False, "未配置 TouchFish 服务器，无法确认注册策略"

    info = tfv5_info(instance)
    if not info:
        return False, "暂时无法确认服务器的注册策略，请稍后再试"

    if "allow_register" not in info:
        # 旧版 TFV5 没有该字段
        return True, ""
    allowed = bool(info.get("allow_register"))
    # 原因只在被拒时返回
    return allowed, "" if allowed else "该 TouchFish 服务器已关闭注册"

from __future__ import annotations

from ..db import Db
from ..settings import Settings
from . import site
from .tfv5 import Instance, Tfv5Error, get_client


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

    try:
        info = get_client().info(instance)
    except Tfv5Error:
        info = None
    if not info:
        return False, "暂时无法确认服务器的注册策略，请稍后再试"

    if "allow_register" not in info:
        # 旧版 TFV5 没有该字段
        return True, ""
    allowed = bool(info.get("allow_register"))
    # 原因只在被拒时返回
    return allowed, "" if allowed else "该 TouchFish 服务器已关闭注册"

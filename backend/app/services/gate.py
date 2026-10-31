"""
登录面的人机验证

登录有人机验证时，所有能"换出会话"的入口都必须过
"""
from __future__ import annotations

from ..db import Db
from . import captcha as captcha_service
from . import throttle


def check_captcha(db: Db, values: dict, token: str | None, *,
                  ip: str, ua: str) -> captcha_service.CaptchaResult | None:
    """通过返回 None；失败返回带原因的 CaptchaResult"""
    result = captcha_service.verify_detail(
        str(values["captcha_provider"]),
        str(values["captcha_secret"]),
        token or "",
        remote_ip=ip,
        verify_url=str(values.get("captcha_verify_url") or ""),
    )
    if result.ok:
        return None
    db.audit(
        "captcha.failed", None, ip, ua,
        detail=f"{result.codes or 'no-codes'} | {result.message} | {result.detail}"[:300],
    )
    return result



def _keys(ip: str, identifier: str) -> tuple[str, str, str]:
    ident = (identifier or "").strip().lower()
    return (f"ip:{ip}", f"acct:{ident}", f"ipacct:{ip}:{ident}")


def login_blocked(values: dict, ip: str, identifier: str) -> int:
    """返回需要等待的秒数 0 表示放行"""
    if not values.get("login_throttle_enabled", True):
        return 0
    throttle.configure(int(values.get("login_max_failures") or 8))
    return throttle.get().blocked_for(*_keys(ip, identifier))


def login_failed(values: dict, ip: str, identifier: str) -> int:
    if not values.get("login_throttle_enabled", True):
        return 0
    throttle.configure(int(values.get("login_max_failures") or 8))
    return throttle.get().fail(*_keys(ip, identifier))


def login_succeeded(ip: str, identifier: str) -> None:
    """成功即清零"""
    throttle.get().reset(*_keys(ip, identifier))

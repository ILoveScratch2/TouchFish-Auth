"""站点配置。
"""
from __future__ import annotations

import time
from typing import Any

from ..db import Db
from ..settings import Settings

# type: bool / int / str / text / enum / secret
SPEC: dict[str, dict[str, Any]] = {
    "site_name": {"type": "str", "max": 64, "category": "general",
                  "label": "站点名称"},
    "announcement": {"type": "text", "max": 500, "category": "general",
                     "label": "登录页公告"},
    "registration_mode": {"type": "enum",
                          "options": ["follow_tfv5", "force_on", "force_off"],
                          "category": "security", "label": "注册策略"},
    "token_ttl": {"type": "int", "min": 60, "max": 86400, "category": "security",
                  "label": "external_token 有效期（秒）"},
    "ticket_ttl": {"type": "int", "min": 30, "max": 600, "category": "security",
                   "label": "ticket 有效期（秒）"},
    "tfv5_login_auto_signup": {"type": "bool", "category": "security",
                               "label": "未绑定的 TouchFish 账号可直接开通平台账户"},
    "login_throttle_enabled": {"type": "bool", "category": "security",
                               "label": "登录连续失败后暂时锁定"},
    "login_max_failures": {"type": "int", "min": 3, "max": 50, "category": "security",
                           "label": "连续失败多少次后开始锁定"},

    "captcha_enabled": {"type": "bool", "category": "captcha",
                        "label": "注册时要求人机验证"},
    "captcha_on_login": {"type": "bool", "category": "captcha",
                         "label": "登录时要求人机验证"},
    "captcha_provider": {"type": "enum", "options": ["turnstile", "hcaptcha"],
                         "category": "captcha", "label": "验证码服务商"},
    "captcha_site_key": {"type": "str", "max": 128, "category": "captcha",
                         "label": "Site Key"},
    "captcha_secret": {"type": "secret", "max": 128, "category": "captcha",
                       "label": "Secret"},
    "captcha_verify_url": {"type": "str", "max": 256, "category": "captcha",
                           "label": "校验地址（留空用官方）"},

    "email_verification": {"type": "bool", "category": "email",
                           "label": "注册后需邮箱验证"},
    "smtp_host": {"type": "str", "max": 128, "category": "email", "label": "SMTP 主机"},
    "smtp_port": {"type": "int", "min": 1, "max": 65535, "category": "email",
                  "label": "SMTP 端口"},
    "smtp_username": {"type": "str", "max": 128, "category": "email", "label": "SMTP 用户名"},
    "smtp_password": {"type": "secret", "max": 256, "category": "email",
                      "label": "SMTP 密码"},
    "smtp_from": {"type": "str", "max": 128, "category": "email", "label": "发件人"},
    "smtp_tls": {"type": "bool", "category": "email", "label": "使用 TLS"},

    # 第三方 OAuth 应用（功能未实现，先把策略定下来，接入时直接生效）
    "oauth_apps_self_service": {"type": "bool", "category": "oauth",
                                "label": "允许普通用户自助创建 OAuth 应用"},
    "oauth_apps_max_per_user": {"type": "int", "min": 1, "max": 100, "category": "oauth",
                                "label": "每个用户的应用上限"},
}

DEFAULTS: dict[str, Any] = {
    "site_name": "",
    "announcement": "",
    "registration_mode": "follow_tfv5",
    "token_ttl": 300,
    "ticket_ttl": 60,
    "tfv5_login_auto_signup": True,
    "login_throttle_enabled": True,
    "login_max_failures": 8,
    "captcha_enabled": False,
    "captcha_on_login": False,
    "captcha_provider": "turnstile",
    "captcha_site_key": "",
    "captcha_secret": "",
    "captcha_verify_url": "",
    "email_verification": False,
    "smtp_host": "",
    "smtp_port": 465,
    "smtp_username": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_tls": True,
    "oauth_apps_self_service": False,
    "oauth_apps_max_per_user": 3,
}


def _coerce(spec: dict[str, Any], raw: Any) -> Any:
    kind = spec["type"]
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if kind == "int":
        return int(raw)
    return str(raw)


def _stored(db: Db) -> dict[str, Any]:
    rows = db.query("SELECT key, value FROM settings")
    return {row["key"]: row["value"] for row in rows}


def all_values(db: Db, settings: Settings) -> dict[str, Any]:
    """合并默认值 + 库中值，并按 spec 做类型转换。"""
    stored = _stored(db)
    result: dict[str, Any] = {}
    for key, spec in SPEC.items():
        default = DEFAULTS.get(key)
        if key == "site_name" and not stored.get(key):
            default = settings.site_name
        if key == "registration_mode" and not stored.get(key):
            default = settings.allow_registration
        if key in stored:
            try:
                result[key] = _coerce(spec, stored[key])
            except (TypeError, ValueError):
                result[key] = default
        else:
            result[key] = default
    return result


def get_value(db: Db, settings: Settings, key: str) -> Any:
    return all_values(db, settings).get(key)


def public_config(db: Db, settings: Settings) -> dict[str, Any]:
    """给未登录页面用的公开配置：不能泄露 secret。"""
    values = all_values(db, settings)
    return {
        "site_name": values["site_name"],
        "announcement": values["announcement"],
        # 客户端据此决定登录页要不要显示"用 TouchFish 账号直接开通"的提示
        "tfv5_login_auto_signup": bool(values["tfv5_login_auto_signup"]),
        "captcha": {
            "enabled": bool(values["captcha_enabled"]),
            "on_login": bool(values["captcha_on_login"]),
            "provider": values["captcha_provider"] if values["captcha_enabled"] or values["captcha_on_login"] else None,
            "site_key": values["captcha_site_key"] if values["captcha_enabled"] or values["captcha_on_login"] else "",
        },
        "email_verification": bool(values["email_verification"]),
        # 第三方应用策略：普通用户也要能看到"能不能自己建、能建几个"
        "oauth_apps": {
            "implemented": False,
            "self_service": bool(values["oauth_apps_self_service"]),
            "max_per_user": int(values["oauth_apps_max_per_user"]),
        },
    }


def admin_view(db: Db, settings: Settings) -> dict[str, Any]:
    """管理端视图：secret 只给"是否已配置"。"""
    values = all_values(db, settings)
    view: dict[str, Any] = {}
    for key, spec in SPEC.items():
        if spec["type"] == "secret":
            view[key] = ""
            view[f"has_{key}"] = bool(values.get(key))
        else:
            view[key] = values[key]
    view["_spec"] = [
        {"key": key, **{k: v for k, v in spec.items()}}
        for key, spec in SPEC.items()
    ]
    return view


class SettingsError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def _validate(spec_name: str, merged: dict[str, Any]) -> None:
    """跨字段校验：别让管理员存下半配置。"""
    if merged["captcha_enabled"] or merged["captcha_on_login"]:
        if not merged["captcha_site_key"]:
            raise SettingsError("captcha_site_key", "启用验证码时必须填写 Site Key")
        if not merged["captcha_secret"]:
            raise SettingsError("captcha_secret", "启用验证码时必须填写 Secret")

    if merged["email_verification"]:
        for key, label in (("smtp_host", "SMTP 主机"), ("smtp_from", "发件人")):
            if not merged[key]:
                raise SettingsError(key, f"启用邮箱验证时必须填写{label}")
        if "@" not in str(merged["smtp_from"]):
            raise SettingsError("smtp_from", "发件人必须是邮箱地址")


def update(db: Db, settings: Settings, changes: dict[str, Any], actor: str) -> dict[str, Any]:
    """局部更新。只接受 SPEC 里的键；empty string 对 secret 表示"保持不变"。"""
    current = all_values(db, settings)
    merged = dict(current)

    for key, raw in changes.items():
        spec = SPEC.get(key)
        if spec is None:
            raise SettingsError(key, f"未知配置项：{key}")
        if spec["type"] == "secret" and (raw is None or raw == ""):
            continue  # 留空 = 不改
        try:
            value = _coerce(spec, raw)
        except (TypeError, ValueError) as exc:
            raise SettingsError(key, f"{spec.get('label', key)} 的值不合法") from exc

        if spec["type"] in ("str", "text", "secret") and "max" in spec:
            if len(str(value)) > int(spec["max"]):
                raise SettingsError(key, f"{spec.get('label', key)} 过长（上限 {spec['max']} 字符）")
        if spec["type"] == "int":
            if value < int(spec.get("min", 0)) or value > int(spec.get("max", 10**9)):
                raise SettingsError(
                    key,
                    f"{spec.get('label', key)} 需在 {spec.get('min')}–{spec.get('max')} 之间",
                )
        if spec["type"] == "enum" and value not in spec["options"]:
            raise SettingsError(key, f"{spec.get('label', key)} 取值不在允许范围")
        merged[key] = value

    _validate("", merged)

    now = time.time()
    for key, raw in changes.items():
        spec = SPEC[key]
        if spec["type"] == "secret" and (raw is None or raw == ""):
            continue
        db.execute(
            "INSERT INTO settings (key, value, is_secret, updated_at, updated_by)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
            " updated_at = excluded.updated_at, updated_by = excluded.updated_by",
            (key, str(merged[key]), 1 if spec["type"] == "secret" else 0, now, actor),
        )
    return merged

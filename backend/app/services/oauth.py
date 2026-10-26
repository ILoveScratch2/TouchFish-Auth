"""第三方 OAuth 登录
fauth作为 client
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from ..db import Db
from ..security import envelope
from ..settings import Settings

STATE_TTL = 600
HTTP_TIMEOUT = 10.0

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")

# pre set for xsfx
TEMPLATES: dict[str, dict[str, str]] = {
    "github": {
        "provider_key": "github",
        "display_name": "GitHub",
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "emails_url": "https://api.github.com/user/emails",
        "scope": "read:user user:email",
        "token_auth_method": "post",
        "uid_field": "id",
        "username_field": "login",
        "email_field": "email",
        "allowed_hosts": "github.com,api.github.com",
    },
    "gitlab": {
        "provider_key": "gitlab",
        "display_name": "GitLab",
        "authorize_url": "https://gitlab.com/oauth/authorize",
        "token_url": "https://gitlab.com/oauth/token",
        "userinfo_url": "https://gitlab.com/api/v4/user",
        "emails_url": "",
        "scope": "read_user",
        "token_auth_method": "post",
        "uid_field": "id",
        "username_field": "username",
        "email_field": "email",
        "allowed_hosts": "gitlab.com",
    },
    "google": {
        "provider_key": "google",
        "display_name": "Google",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "emails_url": "",
        "scope": "openid email profile",
        "token_auth_method": "post",
        "uid_field": "sub",
        "username_field": "email",
        "email_field": "email",
        "allowed_hosts": "accounts.google.com",
    },
    "oidc": {
        "provider_key": "",
        "display_name": "",
        "authorize_url": "",
        "token_url": "",
        "userinfo_url": "",
        "emails_url": "",
        "scope": "openid email profile",
        "token_auth_method": "post",
        "uid_field": "sub",
        "username_field": "preferred_username",
        "email_field": "email",
        "allowed_hosts": "",
    },
}


class OAuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ProviderError(Exception):

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def _sign(settings: Settings, raw: str) -> str:
    return hmac.new(settings.master_key, raw.encode("utf-8"),
                    hashlib.sha256).hexdigest()[:32]


def make_state(settings: Settings, provider: str, redirect: str,
               mode: str = "login", user_id: str = "") -> str:
    raw = f"{provider}\n{redirect}\n{int(time.time())}\n{mode}\n{user_id}"
    return base64.urlsafe_b64encode(
        f"{raw}\n{_sign(settings, raw)}".encode("utf-8")
    ).decode("ascii")


def parse_state(settings: Settings, state: str) -> tuple[str, str, str, str] | None:
    try:
        decoded = base64.urlsafe_b64decode(state.encode("ascii")).decode("utf-8")
        raw, signature = decoded.rsplit("\n", 1)
    except Exception:  # noqa: BLE001 - 畸形 state 一律视为无效
        return None
    if not hmac.compare_digest(signature, _sign(settings, raw)):
        return None
    parts = raw.split("\n")
    if len(parts) == 3:
        provider, redirect, issued = parts
        mode, user_id = "login", ""
    elif len(parts) == 5:
        provider, redirect, issued, mode, user_id = parts
    else:
        return None
    if mode not in ("login", "bind"):
        return None
    try:
        age = time.time() - int(issued)
    except ValueError:
        return None
    if age > STATE_TTL or age < -60:
        return None
    return provider, redirect, mode, user_id


def _hosts(raw: str) -> list[str]:
    return [item.strip().lower() for item in (raw or "").split(",") if item.strip()]


def _to_cfg(row, settings: Settings) -> dict[str, Any]:
    secret = ""
    blob = row["client_secret_enc"]
    if blob:
        try:
            secret = envelope.unseal(settings.master_key, blob)
        except envelope.EnvelopeError:
            secret = ""
    return {
        "id": row["provider_key"],
        "db_id": row["id"],
        "name": row["display_name"],
        "client_id": row["client_id"],
        "client_secret": secret,
        "authorize_url": row["authorize_url"],
        "token_url": row["token_url"],
        "userinfo_url": row["userinfo_url"],
        "emails_url": row["emails_url"] or "",
        "scope": row["scope"] or "",
        "token_auth_method": row["token_auth_method"] or "post",
        "uid_field": row["uid_field"] or "id",
        "username_field": row["username_field"] or "login",
        "email_field": row["email_field"] or "email",
        "allowed_hosts": _hosts(row["allowed_hosts"]),
        "enabled": bool(row["enabled"]),
    }


def _is_complete(cfg: dict[str, Any]) -> bool:
    return bool(cfg["client_id"] and cfg["client_secret"]
                and cfg["authorize_url"] and cfg["token_url"]
                and cfg["userinfo_url"])


def list_all(db: Db, settings: Settings) -> list[dict[str, Any]]:
    rows = db.query("SELECT * FROM oauth_providers ORDER BY display_name")
    return [_to_cfg(row, settings) for row in rows]


def resolve(db: Db, settings: Settings, provider_key: str) -> dict[str, Any] | None:
    row = db.query_one(
        "SELECT * FROM oauth_providers WHERE provider_key = ?", (provider_key,))
    if row is None or not row["enabled"]:
        return None
    cfg = _to_cfg(row, settings)
    return cfg if _is_complete(cfg) else None


def public(db: Db, settings: Settings) -> list[dict[str, str]]:
    return [{"id": cfg["id"], "name": cfg["name"]}
            for cfg in list_all(db, settings)
            if cfg["enabled"] and _is_complete(cfg)]


def methods(db: Db, settings: Settings, base_url: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for cfg in list_all(db, settings):
        if not cfg["enabled"] or not _is_complete(cfg):
            continue
        result.append({
            "id": cfg["id"],
            "kind": "oauth2",
            "display_name": cfg["name"],
            "enabled": True,
            "start_url": f"{base_url}/api/auth/oauth/{cfg['id']}/start",
            "allowed_hosts": cfg["allowed_hosts"],
        })
    return result


def admin_view(db: Db, settings: Settings) -> list[dict[str, Any]]:
    counts = {
        row["provider"]: row["n"] for row in db.query(
            "SELECT provider, COUNT(*) AS n FROM oauth_accounts GROUP BY provider")
    }
    result: list[dict[str, Any]] = []
    for cfg in list_all(db, settings):
        result.append({
            "id": cfg["db_id"],
            "provider_key": cfg["id"],
            "display_name": cfg["name"],
            "client_id": cfg["client_id"],
            "client_secret_set": bool(cfg["client_secret"]),
            "authorize_url": cfg["authorize_url"],
            "token_url": cfg["token_url"],
            "userinfo_url": cfg["userinfo_url"],
            "emails_url": cfg["emails_url"],
            "scope": cfg["scope"],
            "token_auth_method": cfg["token_auth_method"],
            "uid_field": cfg["uid_field"],
            "username_field": cfg["username_field"],
            "email_field": cfg["email_field"],
            "allowed_hosts": ",".join(cfg["allowed_hosts"]),
            "enabled": cfg["enabled"],
            "complete": _is_complete(cfg),
            "linked_accounts": int(counts.get(cfg["id"], 0)),
        })
    return result


def _require_http_url(field: str, value: str, required: bool) -> str:
    value = (value or "").strip()
    if not value:
        if required:
            raise ProviderError(field, "该地址不能为空")
        return ""
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ProviderError(field, "必须是 http(s) 绝对地址")
    if len(value) > 256:
        raise ProviderError(field, "地址过长（上限 256 字符）")
    return value


def _validate(payload: dict[str, Any], *, creating: bool,
              current_key: str | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}

    key = str(payload.get("provider_key") or "").strip().lower()
    if creating or (key and key != current_key):
        if not KEY_RE.match(key):
            raise ProviderError(
                "provider_key",
                "标识需为 2–32 位小写字母/数字/下划线/连字符，且以字母或数字开头",
            )
        cleaned["provider_key"] = key

    name = str(payload.get("display_name") or "").strip()
    if not name or len(name) > 48:
        raise ProviderError("display_name", "显示名需为 1–48 个字符")
    cleaned["display_name"] = name

    client_id = str(payload.get("client_id") or "").strip()
    if not client_id or len(client_id) > 200:
        raise ProviderError("client_id", "Client ID 不能为空且不超过 200 字符")
    cleaned["client_id"] = client_id

    cleaned["authorize_url"] = _require_http_url(
        "authorize_url", payload.get("authorize_url"), True)
    cleaned["token_url"] = _require_http_url(
        "token_url", payload.get("token_url"), True)
    cleaned["userinfo_url"] = _require_http_url(
        "userinfo_url", payload.get("userinfo_url"), True)
    cleaned["emails_url"] = _require_http_url(
        "emails_url", payload.get("emails_url"), False)

    scope = str(payload.get("scope") or "").strip()
    if len(scope) > 200:
        raise ProviderError("scope", "scope 过长（上限 200 字符）")
    cleaned["scope"] = scope

    auth_method = str(payload.get("token_auth_method") or "post").strip().lower()
    if auth_method not in ("post", "basic"):
        raise ProviderError("token_auth_method", "令牌端点认证方式只能是 post 或 basic")
    cleaned["token_auth_method"] = auth_method

    for field, default in (("uid_field", "id"), ("username_field", "login"),
                           ("email_field", "email")):
        value = str(payload.get(field) or "").strip() or default
        if not re.match(r"^[A-Za-z0-9_.-]{1,48}$", value):
            raise ProviderError(field, "字段名只能包含字母、数字、下划线、点或连字符")
        cleaned[field] = value

    hosts = str(payload.get("allowed_hosts") or "").strip()
    if len(hosts) > 300:
        raise ProviderError("allowed_hosts", "域名列表过长（上限 300 字符）")
    parsed = _hosts(hosts)
    for host in parsed:
        if not re.match(r"^([a-z0-9*_-]+\.)+[a-z0-9-]+$", host):
            raise ProviderError("allowed_hosts", f"域名不合法：{host}")
    if not parsed:
        parsed = [urlsplit(cleaned["authorize_url"]).hostname or ""]
        parsed = [host for host in parsed if host]
    cleaned["allowed_hosts"] = ",".join(parsed)

    cleaned["enabled"] = bool(payload.get("enabled", True))
    return cleaned


def create(db: Db, settings: Settings, payload: dict[str, Any]) -> str:
    data = _validate(payload, creating=True, current_key=None)
    if db.query_one("SELECT 1 FROM oauth_providers WHERE provider_key = ?",
                    (data["provider_key"],)):
        raise ProviderError("provider_key", "该标识已被占用")

    secret = str(payload.get("client_secret") or "").strip()
    if not secret:
        raise ProviderError("client_secret", "Client Secret 不能为空")
    now = time.time()
    db.execute(
        "INSERT INTO oauth_providers (id, provider_key, display_name, client_id,"
        " client_secret_enc, authorize_url, token_url, userinfo_url, emails_url,"
        " scope, token_auth_method, uid_field, username_field, email_field,"
        " allowed_hosts, enabled, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (secrets.token_hex(12), data["provider_key"], data["display_name"],
         data["client_id"], envelope.seal(settings.master_key, secret),
         data["authorize_url"], data["token_url"], data["userinfo_url"],
         data["emails_url"] or None, data["scope"], data["token_auth_method"],
         data["uid_field"], data["username_field"], data["email_field"],
         data["allowed_hosts"], 1 if data["enabled"] else 0, now, now),
    )
    return data["provider_key"]


def update(db: Db, settings: Settings, provider_id: str,
           payload: dict[str, Any]) -> str:
    """局部更新：没传的字段沿用原值（前端可以只提交改动项）。"""
    row = db.query_one("SELECT * FROM oauth_providers WHERE id = ?", (provider_id,))
    if row is None:
        raise ProviderError("id", "provider 不存在")

    merged: dict[str, Any] = {
        "provider_key": row["provider_key"],
        "display_name": row["display_name"],
        "client_id": row["client_id"],
        "authorize_url": row["authorize_url"],
        "token_url": row["token_url"],
        "userinfo_url": row["userinfo_url"],
        "emails_url": row["emails_url"] or "",
        "scope": row["scope"] or "",
        "token_auth_method": row["token_auth_method"] or "post",
        "uid_field": row["uid_field"],
        "username_field": row["username_field"],
        "email_field": row["email_field"],
        "allowed_hosts": row["allowed_hosts"] or "",
        "enabled": bool(row["enabled"]),
    }
    merged.update({key: value for key, value in payload.items()
                   if value is not None})

    data = _validate(merged, creating=False, current_key=row["provider_key"])
    new_key = data.get("provider_key")
    if new_key and new_key != row["provider_key"]:
        if db.query_one("SELECT 1 FROM oauth_providers WHERE provider_key = ?",
                        (new_key,)):
            raise ProviderError("provider_key", "该标识已被占用")
        linked = db.query_one(
            "SELECT COUNT(*) AS n FROM oauth_accounts WHERE provider = ?",
            (row["provider_key"],))
        if linked and int(linked["n"]) > 0:
            # oauth_accounts 用 provider_key 做关联，直接改名会让这些绑定失联
            raise ProviderError(
                "provider_key",
                f"已有 {int(linked['n'])} 个账号绑定该平台，修改标识会导致它们无法登录",
            )

    secret = str(payload.get("client_secret") or "").strip()
    blob = row["client_secret_enc"]
    if secret:
        blob = envelope.seal(settings.master_key, secret)

    db.execute(
        "UPDATE oauth_providers SET provider_key = ?, display_name = ?,"
        " client_id = ?, client_secret_enc = ?, authorize_url = ?, token_url = ?,"
        " userinfo_url = ?, emails_url = ?, scope = ?, token_auth_method = ?,"
        " uid_field = ?, username_field = ?, email_field = ?, allowed_hosts = ?,"
        " enabled = ?, updated_at = ? WHERE id = ?",
        (new_key or row["provider_key"], data["display_name"], data["client_id"],
         blob, data["authorize_url"], data["token_url"], data["userinfo_url"],
         data["emails_url"] or None, data["scope"], data["token_auth_method"],
         data["uid_field"], data["username_field"], data["email_field"],
         data["allowed_hosts"], 1 if data["enabled"] else 0, time.time(),
         provider_id),
    )
    return new_key or row["provider_key"]


def delete(db: Db, provider_id: str, *, force: bool = False) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM oauth_providers WHERE id = ?", (provider_id,))
    if row is None:
        raise ProviderError("id", "provider 不存在")
    linked = db.query_one(
        "SELECT COUNT(*) AS n FROM oauth_accounts WHERE provider = ?",
        (row["provider_key"],))
    count = int(linked["n"]) if linked else 0
    if count and not force:
        raise ProviderError(
            "in_use",
            f"仍有 {count} 个账号绑定该平台，删除后这些账号将无法用它登录",
        )
    db.execute("DELETE FROM oauth_providers WHERE id = ?", (provider_id,))
    return {"provider_key": row["provider_key"], "linked_accounts": count}


def migrate_legacy(db: Db, settings: Settings) -> None:
    if db.query_one("SELECT 1 FROM oauth_providers LIMIT 1"):
        return
    rows = {row["key"]: row["value"] for row in db.query(
        "SELECT key, value FROM settings WHERE key LIKE 'oauth_github_%'")}
    client_id = (rows.get("oauth_github_client_id") or "").strip()
    secret = (rows.get("oauth_github_client_secret") or "").strip()
    if not client_id or not secret:
        return

    template = dict(TEMPLATES["github"])
    override = {
        "authorize_url": rows.get("oauth_github_authorize_url"),
        "token_url": rows.get("oauth_github_token_url"),
        "userinfo_url": rows.get("oauth_github_userinfo_url"),
        "emails_url": rows.get("oauth_github_emails_url"),
    }
    for key, value in override.items():
        if value and str(value).strip():
            template[key] = str(value).strip()

    now = time.time()
    try:
        db.execute(
            "INSERT INTO oauth_providers (id, provider_key, display_name, client_id,"
            " client_secret_enc, authorize_url, token_url, userinfo_url, emails_url,"
            " scope, token_auth_method, uid_field, username_field, email_field,"
            " allowed_hosts, enabled, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (secrets.token_hex(12), "github", "GitHub", client_id,
             envelope.seal(settings.master_key, secret),
             template["authorize_url"], template["token_url"],
             template["userinfo_url"], template["emails_url"] or None,
             template["scope"], template.get("token_auth_method", "post"),
             template["uid_field"], template["username_field"],
             template["email_field"], template["allowed_hosts"],
             1 if str(rows.get("oauth_github_enabled", "")).lower() in
             ("1", "true", "yes", "on") else 0, now, now),
        )
    except Exception:  # noqa: BLE001 - 迁移失败不应阻断启动
        return


def authorize_url(cfg: dict, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "scope": cfg["scope"],
        "state": state,
        "response_type": "code",
    }
    return f"{cfg['authorize_url']}?{urlencode(params)}"


def fetch_profile(cfg: dict, code: str, redirect_uri: str) -> dict:
    """用授权码换 token 并拉取资料，按配置的字段名取值。"""
    token_data = {
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "client_id": cfg["client_id"],
    }
    basic = cfg.get("token_auth_method") == "basic"
    auth: tuple[str, str] | None = None
    if basic:
        auth = (cfg["client_id"], cfg["client_secret"])
    else:
        token_data["client_secret"] = cfg["client_secret"]

    try:
        token_resp = httpx.post(
            cfg["token_url"],
            data=token_data,
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=HTTP_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise OAuthError("provider_unreachable",
                         f"无法连接 {cfg['name']}：{exc}") from exc

    access_token = _access_token(token_resp)
    if not access_token:
        raise OAuthError("token_failed", f"{cfg['name']} 未返回访问令牌")

    headers = {"Authorization": f"Bearer {access_token}",
               "Accept": "application/json"}
    try:
        user = _json(httpx.get(cfg["userinfo_url"], headers=headers,
                               timeout=HTTP_TIMEOUT))
    except httpx.HTTPError as exc:
        raise OAuthError("provider_unreachable",
                         f"无法读取 {cfg['name']} 账号信息：{exc}") from exc

    uid = _pick(user, cfg["uid_field"], "sub", "id", "user_id", "uid")
    if uid is None or str(uid).strip() == "":
        raise OAuthError("profile_failed",
                         f"{cfg['name']} 未返回账号标识（检查「标识字段」配置）")

    email, verified = "", False
    raw_email = str(_pick(user, cfg["email_field"], "email") or "").strip().lower()
    if raw_email and "@" in raw_email:
        email = raw_email
        verified = _is_true(_pick(user, "email_verified", "verified_email", "verified"))

    if cfg["emails_url"]:
        try:
            mails = _json_list(httpx.get(cfg["emails_url"], headers=headers,
                                         timeout=HTTP_TIMEOUT))
        except httpx.HTTPError:
            mails = []
        primary = next((m for m in mails if m.get("primary") and m.get("verified")), None)
        fallback = next((m for m in mails if m.get("verified")), None)
        chosen = primary or fallback
        if chosen:
            candidate = str(chosen.get("email") or "").strip().lower()
            if candidate and "@" in candidate:
                email, verified = candidate, True

    username = str(_pick(user, cfg["username_field"], "login", "username",
                         "preferred_username", "nickname", "name") or "").strip()
    if not username:
        username = email.split("@")[0] if email else f"{cfg['id']}_user"

    return {
        "provider": cfg["id"],
        "provider_uid": str(uid),
        "login": username[:64],
        "display_name": str(_pick(user, "name", "display_name", "full_name") or ""),
        "email": email if verified else "",
        "email_verified": bool(verified and email),
        "avatar_url": str(_pick(user, "avatar_url", "picture", "avatar") or ""),
    }


def _pick(payload: dict, *names: str) -> Any:
    for name in names:
        if not name:
            continue
        if name in payload and payload[name] not in (None, ""):
            return payload[name]
    return None


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def _access_token(response: httpx.Response) -> str:
    if response.status_code >= 400:
        return ""
    body = response.text
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        token = data.get("access_token")
        return str(token) if token else ""
    # application/x-www-form-urlencoded
    parsed = parse_qs(body)
    token = (parsed.get("access_token") or [""])[0]
    return str(token)


def _json(response: httpx.Response) -> dict:
    if response.status_code >= 400:
        return {}
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _json_list(response: httpx.Response) -> list:
    if response.status_code >= 400:
        return []
    try:
        data = response.json()
    except ValueError:
        return []
    return data if isinstance(data, list) else []



def account_for(db: Db, provider: str, provider_uid: str) -> dict | None:
    return db.query_one(
        "SELECT * FROM oauth_accounts WHERE provider = ? AND provider_uid = ?",
        (provider, provider_uid),
    )


def list_accounts(db: Db, user_id: str) -> list[dict]:
    return db.query(
        "SELECT provider, provider_uid, email, login, avatar_url, linked_at"
        " FROM oauth_accounts WHERE user_id = ? ORDER BY linked_at",
        (user_id,),
    )


def link_account(db: Db, user_id: str, profile: dict) -> None:
    existing = account_for(db, profile["provider"], profile["provider_uid"])
    if existing is not None:
        if existing["user_id"] != user_id:
            raise OAuthError("provider_already_bound",
                             "该第三方账号已绑定到另一个平台账号")
        db.execute(
            "UPDATE oauth_accounts SET email = ?, login = ?, avatar_url = ?"
            " WHERE id = ?",
            (profile["email"] or None, profile["login"] or None,
             profile["avatar_url"] or None, existing["id"]),
        )
        return

    same_provider = db.query_one(
        "SELECT id FROM oauth_accounts WHERE user_id = ? AND provider = ?",
        (user_id, profile["provider"]),
    )
    if same_provider is not None:
        raise OAuthError("provider_in_use",
                         "该账号已绑定另一个同类第三方账号，请先解绑")

    try:
        db.execute(
            "INSERT INTO oauth_accounts (id, user_id, provider, provider_uid,"
            " email, login, avatar_url, linked_at) VALUES (?,?,?,?,?,?,?,?)",
            (secrets.token_hex(12), user_id, profile["provider"],
             profile["provider_uid"], profile["email"] or None,
             profile["login"] or None, profile["avatar_url"] or None,
             time.time()),
        )
    except Exception as exc:  # noqa: BLE001 - 并发下的唯一约束
        raise OAuthError("provider_already_bound",
                         "该第三方账号已绑定到另一个平台账号") from exc


def unlink_account(db: Db, user_id: str, provider: str) -> None:
    row = db.query_one(
        "SELECT id FROM oauth_accounts WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    )
    if row is None:
        raise OAuthError("not_linked", "尚未绑定该平台")
    db.execute("DELETE FROM oauth_accounts WHERE id = ?", (row["id"],))

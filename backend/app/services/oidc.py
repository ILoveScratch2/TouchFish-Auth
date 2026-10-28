"""本平台作为 OAuth2 / OIDC 授权服务器
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any

from ..db import Db
from ..security.passwords import hash_password, verify_password

CODE_TTL = 60.0
ACCESS_TTL = 3600.0
REFRESH_TTL = 30 * 86400.0

# 当前支持的全部 scope
# 新增时要同步 well-known 的 scopes_supported
SUPPORTED_SCOPES = ("openid", "profile", "email")


class OidcError(Exception):
    """端点层统一转成 OAuth2 的 error 对象（/token）或 302（/authorize）。"""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------- 客户端注册

def redirect_list(raw: str | None) -> list[str]:
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def scope_list(raw: str | None) -> list[str]:
    return [item for item in (raw or "").split() if item]


def normalize_scopes(requested: str | None, allowed: str | None) -> str:
    """把请求的 scope 收敛到客户端允许的范围。

    未请求 scope 时回落到客户端的默认集（必含 openid，否则拿不到 id_token）。
    请求了未授权的 scope 直接拒绝，而不是静默丢弃——静默丢弃会让
    调用方以为拿到了权限。
    """
    allowed_set = set(scope_list(allowed)) or set(SUPPORTED_SCOPES)
    requested_list = scope_list(requested)
    if not requested_list:
        requested_list = [item for item in ("openid", "profile", "email")
                          if item in allowed_set]
    unknown = [item for item in requested_list if item not in SUPPORTED_SCOPES]
    if unknown:
        raise OidcError("invalid_scope", f"不支持的 scope: {', '.join(unknown)}")
    denied = [item for item in requested_list if item not in allowed_set]
    if denied:
        raise OidcError("invalid_scope",
                        f"该客户端未获授权使用: {', '.join(denied)}")
    return " ".join(dict.fromkeys(requested_list))  # 去重并保持顺序


def public_view(row: Any) -> dict[str, Any]:
    """管理端列表用：绝不回显 secret，只说明是否设置过。"""
    return {
        "client_id": row["client_id"],
        "name": row["client_name"],
        "redirect_uris": redirect_list(row["redirect_uris"]),
        "scopes": scope_list(row["scopes"]),
        "is_public": row["secret_hash"] is None,
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
    }


def find_client(db: Db, client_id: str) -> Any | None:
    return db.query_one(
        "SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,))


def list_clients(db: Db, owner_id: str | None = None) -> list[dict[str, Any]]:
    """owner_id 为 None 时返回全部（管理员视角）。"""
    if owner_id is None:
        rows = db.query("SELECT * FROM oauth_clients ORDER BY created_at DESC")
    else:
        rows = db.query(
            "SELECT * FROM oauth_clients WHERE owner_id = ? ORDER BY created_at DESC",
            (owner_id,))
    return [public_view(row) for row in rows]


def _validate_redirect_uris(uris: list[str]) -> None:
    if not uris:
        raise OidcError("invalid_redirect_uri", "至少需要一个回调地址")
    for uri in uris:
        if not (uri.startswith("http://") or uri.startswith("https://")):
            raise OidcError("invalid_redirect_uri",
                            f"回调地址必须是 http(s) 绝对地址：{uri}")
        if "#" in uri:
            raise OidcError("invalid_redirect_uri",
                            f"回调地址不能带 fragment：{uri}")


def create_client(db: Db, name: str, redirect_uris: list[str],
                  scopes: list[str], public: bool,
                  owner_id: str | None = None) -> tuple[dict[str, Any], str | None]:
    """返回 (client_view, 明文 secret)。公开客户端 secret 为 None。

    `owner_id` 为 None 表示管理员创建，不占用户自助配额。
    """
    name = (name or "").strip()
    if not name:
        raise OidcError("invalid_client_name", "客户端名称不能为空")
    _validate_redirect_uris(redirect_uris)

    wanted = [item for item in scopes if item] or ["openid", "profile", "email"]
    unknown = [item for item in wanted if item not in SUPPORTED_SCOPES]
    if unknown:
        raise OidcError("invalid_scope", f"不支持的 scope: {', '.join(unknown)}")
    if "openid" not in wanted:
        wanted.insert(0, "openid")

    client_id = "tf_" + secrets.token_hex(8)
    secret = None if public else secrets.token_urlsafe(32)
    now = time.time()
    db.execute(
        "INSERT INTO oauth_clients (id, client_id, client_name, secret_hash,"
        " redirect_uris, scopes, owner_id, enabled, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (secrets.token_hex(12), client_id, name,
         None if public else hash_password(secret or ""),
         "\n".join(redirect_uris), " ".join(dict.fromkeys(wanted)),
         owner_id, 1, now, now),
    )
    row = find_client(db, client_id)
    return public_view(row), secret


def update_client(db: Db, client_id: str, name: str | None = None,
                  redirect_uris: list[str] | None = None,
                  scopes: list[str] | None = None,
                  enabled: bool | None = None) -> dict[str, Any]:
    row = find_client(db, client_id)
    if row is None:
        raise OidcError("client_not_found", "客户端不存在", 404)

    updates: dict[str, Any] = {}
    if name is not None:
        if not name.strip():
            raise OidcError("invalid_client_name", "客户端名称不能为空")
        updates["client_name"] = name.strip()
    if redirect_uris is not None:
        _validate_redirect_uris(redirect_uris)
        updates["redirect_uris"] = "\n".join(redirect_uris)
    if scopes is not None:
        unknown = [item for item in scopes if item not in SUPPORTED_SCOPES]
        if unknown:
            raise OidcError("invalid_scope", f"不支持的 scope: {', '.join(unknown)}")
        if "openid" not in scopes:
            scopes = ["openid", *scopes]
        updates["scopes"] = " ".join(dict.fromkeys(scopes))
    if enabled is not None:
        updates["enabled"] = 1 if enabled else 0

    if updates:
        updates["updated_at"] = time.time()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        db.execute(f"UPDATE oauth_clients SET {assignments} WHERE client_id = ?",
                   (*updates.values(), client_id))
    return public_view(find_client(db, client_id))


def rotate_secret(db: Db, client_id: str) -> str:
    row = find_client(db, client_id)
    if row is None:
        raise OidcError("client_not_found", "客户端不存在", 404)
    if row["secret_hash"] is None:
        raise OidcError("public_client", "公开客户端没有 secret，请改用 PKCE", 400)
    secret = secrets.token_urlsafe(32)
    db.execute(
        "UPDATE oauth_clients SET secret_hash = ?, updated_at = ? WHERE client_id = ?",
        (hash_password(secret), time.time(), client_id),
    )
    return secret


def delete_client(db: Db, client_id: str) -> None:
    row = find_client(db, client_id)
    if row is None:
        raise OidcError("client_not_found", "客户端不存在", 404)
    now = time.time()
    # 只停用不删即可保留审计线索，但客户端要求删除时应当真正失效：
    # 连带吊销它名下所有令牌。
    db.execute("UPDATE oauth_access_tokens SET revoked_at = ?"
               " WHERE client_id = ? AND revoked_at IS NULL", (now, client_id))
    db.execute("UPDATE oauth_refresh_tokens SET revoked_at = ?"
               " WHERE client_id = ? AND revoked_at IS NULL", (now, client_id))
    db.execute("DELETE FROM oauth_codes WHERE client_id = ?", (client_id,))
    db.execute("DELETE FROM oauth_clients WHERE client_id = ?", (client_id,))


def verify_client_secret(db: Db, client_id: str, secret: str) -> bool:
    """confidential 客户端的凭据校验。公开客户端一律 False（只能走 PKCE）。"""
    row = find_client(db, client_id)
    if row is None or row["secret_hash"] is None:
        return False
    return verify_password(row["secret_hash"], secret)


# ---------------------------------------------------------------- 授权请求

def check_authorize_request(db: Db, client_id: str, redirect_uri: str,
                            response_type: str, scope: str | None,
                            code_challenge: str | None,
                            code_challenge_method: str | None,
                            state: str | None, nonce: str | None) -> dict[str, Any]:
    """校验 /authorize 的参数。任何一项不合法都必须**在跳转之前**失败——
    否则会把错误发到未验证的 redirect_uri 上（开放重定向）。
    """
    row = find_client(db, client_id)
    if row is None or not row["enabled"]:
        raise OidcError("invalid_client", "未知或已停用的客户端", 400)
    if response_type != "code":
        raise OidcError("unsupported_response_type", "只支持 response_type=code")
    if not redirect_uri or redirect_uri not in redirect_list(row["redirect_uris"]):
        raise OidcError("invalid_redirect_uri",
                        "回调地址与注册值不一致（必须逐字符相同）")

    method = (code_challenge_method or "").upper() or None
    challenge = (code_challenge or "").strip() or None
    if challenge is not None and method != "S256":
        # 只支持 S256：plain 等于把 verifier 明文放进授权请求，
        # 一旦授权码被截获就失去意义。
        raise OidcError("invalid_request", "code_challenge_method 只支持 S256")
    if challenge is None and row["secret_hash"] is None:
        # 公开客户端没有 secret，PKCE 是唯一的代码换取凭证的保护
        raise OidcError("invalid_request", "公开客户端必须使用 PKCE（code_challenge）")

    return {
        "client": row,
        "client_id": client_id,
        "client_name": row["client_name"],
        "redirect_uri": redirect_uri,
        "scope": normalize_scopes(scope, row["scopes"]),
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": method,
    }


def issue_code(db: Db, request: dict[str, Any], user_id: str) -> str:
    code = secrets.token_urlsafe(32)
    now = time.time()
    db.execute(
        "INSERT INTO oauth_codes (code_hash, client_id, user_id, redirect_uri,"
        " scope, code_challenge, code_challenge_method, nonce, created_at, expires_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (_sha256(code), request["client_id"], user_id, request["redirect_uri"],
         request["scope"], request["code_challenge"],
         request["code_challenge_method"], request["nonce"],
         now, now + CODE_TTL),
    )
    return code


def _verify_pkce(challenge: str, method: str | None, verifier: str | None) -> bool:
    if not verifier:
        return False
    if len(verifier) < 43 or len(verifier) > 128:
        return False
    if (method or "S256").upper() != "S256":
        return False
    try:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
    except UnicodeEncodeError:
        # 非 ASCII 的 verifier 不可能与 S256 challenge 对上
        return False
    return secrets.compare_digest(_b64url(digest), challenge)


def redeem_code(db: Db, client_id: str, code: str, redirect_uri: str,
                verifier: str | None) -> dict[str, Any]:
    """兑换授权码。成功即标记已用（重放会被拒绝）。"""
    row = db.query_one(
        "SELECT * FROM oauth_codes WHERE code_hash = ?", (_sha256(code),))
    if row is None:
        raise OidcError("invalid_grant", "授权码无效")
    if row["consumed_at"] is not None:
        raise OidcError("invalid_grant", "授权码已被使用")
    if row["expires_at"] < time.time():
        raise OidcError("invalid_grant", "授权码已过期")
    if row["client_id"] != client_id:
        raise OidcError("invalid_grant", "授权码不属于该客户端")
    if row["redirect_uri"] != redirect_uri:
        raise OidcError("invalid_grant", "redirect_uri 与授权时不一致")
    if row["code_challenge"] is not None:
        if not _verify_pkce(row["code_challenge"], row["code_challenge_method"],
                            verifier):
            raise OidcError("invalid_grant", "code_verifier 校验失败")
    # 没有 challenge 说明是机密客户端（公开客户端在 /authorize 阶段被强制要求 PKCE），
    # 此时 PKCE 是可选的：不能再要求 code_verifier，否则这类客户端永远兑换不了。

    consumed = db.execute(
        "UPDATE oauth_codes SET consumed_at = ? WHERE code_hash = ?"
        " AND consumed_at IS NULL", (time.time(), _sha256(code)))
    if consumed == 0:  # 并发下的双花
        raise OidcError("invalid_grant", "授权码已被使用")

    return {"user_id": row["user_id"], "scope": row["scope"],
            "nonce": row["nonce"]}


# ---------------------------------------------------------------- 令牌签发

def _claims_for_user(db: Db, user_id: str, scope: str) -> dict[str, Any]:
    row = db.query_one(
        "SELECT id, username, display_name, email, email_key, status"
        " FROM users WHERE id = ?",
        (user_id,),
    )
    if row is None:
        raise OidcError("invalid_grant", "账号已不存在")
    claims: dict[str, Any] = {"sub": row["id"]}
    scopes = set(scope_list(scope))
    if "profile" in scopes:
        claims["preferred_username"] = row["username"]
        claims["name"] = row["display_name"] or row["username"]
    if "email" in scopes and row["email"]:
        claims["email"] = row["email"]
        # email_key 在"注册但未验证"时也会写入（status=pending），
        # 所以不能只看它存在：pending 账号一律报未验证。
        claims["email_verified"] = bool(row["email_key"]) and row["status"] != "pending"
    return claims


def issue_tokens(db: Db, keystore: Any, settings: Any, client_id: str,
                 user_id: str, scope: str,
                 nonce: str | None = None) -> dict[str, Any]:
    now = time.time()
    scopes = set(scope_list(scope))

    access = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO oauth_access_tokens (token_hash, client_id, user_id, scope,"
        " created_at, expires_at) VALUES (?,?,?,?,?,?)",
        (_sha256(access), client_id, user_id, scope, now, now + ACCESS_TTL),
    )

    refresh = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO oauth_refresh_tokens (token_hash, client_id, user_id, scope,"
        " created_at, expires_at) VALUES (?,?,?,?,?,?)",
        (_sha256(refresh), client_id, user_id, scope, now, now + REFRESH_TTL),
    )

    result: dict[str, Any] = {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": int(ACCESS_TTL),
        "refresh_token": refresh,
        "scope": scope,
    }

    if "openid" in scopes:
        claims: dict[str, Any] = {
            "iss": settings.issuer,
            "aud": client_id,
            "iat": int(now),
            "nbf": int(now),
            "exp": int(now + ACCESS_TTL),
            "jti": secrets.token_hex(16),
            # 与 TFV5 的外部登录令牌区分开：TFV5 只接受 token_use 为空的旧令牌
            # 或显式标记 tfv5 的令牌，id_token 不该能在那边换会话。
            "token_use": "id",
            "auth_time": int(now),
            **_claims_for_user(db, user_id, scope),
        }
        if nonce:
            claims["nonce"] = nonce
        result["id_token"] = keystore.sign(claims)

    return result


def resolve_access(db: Db, token: str) -> dict[str, Any]:
    row = db.query_one(
        "SELECT * FROM oauth_access_tokens WHERE token_hash = ?", (_sha256(token),))
    if row is None or row["revoked_at"] is not None or row["expires_at"] < time.time():
        raise OidcError("invalid_token", "访问令牌无效或已过期", 401)
    return row


def userinfo(db: Db, token: str) -> dict[str, Any]:
    row = resolve_access(db, token)
    claims = _claims_for_user(db, row["user_id"], row["scope"])
    return claims


def rotate_refresh(db: Db, keystore: Any, settings: Any, client_id: str,
                   refresh_token: str) -> dict[str, Any]:
    row = db.query_one(
        "SELECT * FROM oauth_refresh_tokens WHERE token_hash = ?",
        (_sha256(refresh_token),))
    if row is None or row["revoked_at"] is not None:
        raise OidcError("invalid_grant", "刷新令牌无效")
    if row["expires_at"] < time.time():
        raise OidcError("invalid_grant", "刷新令牌已过期")
    if row["client_id"] != client_id:
        raise OidcError("invalid_grant", "刷新令牌不属于该客户端")

    revoked = db.execute(
        "UPDATE oauth_refresh_tokens SET revoked_at = ? WHERE token_hash = ?"
        " AND revoked_at IS NULL", (time.time(), _sha256(refresh_token)))
    if revoked == 0:
        raise OidcError("invalid_grant", "刷新令牌已被使用")

    return issue_tokens(db, keystore, settings, client_id, row["user_id"],
                        row["scope"])

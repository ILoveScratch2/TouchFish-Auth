"""绑定编排：平台账户 ↔ TFV5 账户。

两条链路：
  platform —— 调 TFV5 的 /auth/platform/bind，只校验 + 写映射，不建会话，
              首选，不会污染用户的设备/会话列表。
  legacy   —— 旧版 TFV5 没有专用端点时，走 login + external/bind，
              会建一个 TFV5 会话，因此把 refresh token 加密存下来
"""
from __future__ import annotations

import time

from ..db import Db
from ..settings import Settings
from ..security import envelope
from ..security.signer import KeyStore
from . import instances as instances_repo
from .tfv5 import Instance, Tfv5Error, get_client


class BindError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _external_token(keystore: KeyStore, settings: Settings, instance: Instance,
                    user_id: str, tfv5_uid: int | None, ttl: int | None = None) -> str:
    now = int(time.time())
    claims: dict = {
        "iss": settings.issuer,
        "sub": user_id,
        "iat": now,
        "nbf": now,
        "exp": now + int(ttl if ttl is not None else settings.token_ttl),
        # 标记用途
        # 避免 OAuth 登录 TF
        # OAuth 不是这么用的
        "token_use": "tfv5",
    }
    if instance.audience:
        claims["aud"] = instance.audience
    if tfv5_uid is not None:
        claims["tfv5_uid"] = tfv5_uid
    return keystore.sign(claims)


def get_connection(db: Db, user_id: str, instance_id: str):
    return db.query_one(
        "SELECT * FROM connections WHERE user_id = ? AND instance_id = ?",
        (user_id, instance_id),
    )


def list_connections(db: Db, user_id: str) -> list[dict]:
    rows = db.query(
        "SELECT c.*, i.display_name, i.base_url FROM connections c"
        " JOIN tfv5_instances i ON i.id = c.instance_id"
        " WHERE c.user_id = ? ORDER BY c.bound_at DESC",
        (user_id,),
    )
    return [
        {
            "id": row["id"],
            "instance_id": row["instance_id"],
            "instance_name": row["display_name"],
            "instance_url": row["base_url"],
            "tfv5_uid": row["tfv5_uid"],
            "tfv5_username": row["tfv5_username"],
            "bind_channel": row["bind_channel"],
            "bound_at": row["bound_at"],
            "last_login_at": row["last_login_at"],
            "has_cached_session": row["refresh_token_enc"] is not None,
        }
        for row in rows
    ]


def bind(db: Db, settings: Settings, user_id: str, instance: Instance,
         identifier: str, password: str, *, assume_platform: bool = False,
         login_reuse: bool = False) -> dict:
    """建立绑定。identifier 可以是用户名或数字 uid。

    `assume_platform=True` 时跳过"端点是否可用"的探测，直接走专用端点。
    调用方已经探测过（例如登录路径在入口就查过 status）时用它，
    否则每次登录都会多打一次 status，把对端的按路径配额吃满。

    `login_reuse=True` 表示这次调用是"登录时复用已有绑定"，只刷新
    `last_login_at`，不动 `bound_at`（前端的"绑定时间"才不会被登录时间覆盖）。
    """
    client = get_client()
    iss = settings.issuer
    touch = not login_reuse

    # 1) 专用端点
    if assume_platform:
        result = client.platform_bind(instance, iss=iss, sub=user_id,
                                      identifier=identifier, password=password)
        if result.get("success") is not True:
            raise _map_error(result.get("error", "bind_failed"))
        uid = int(result.get("uid") or 0)
        username = str(result.get("username") or identifier)
        _upsert_connection(db, user_id, instance, uid, username, "platform", None,
                           refresh_bound_at=touch)
        return {"ok": True, "channel": "platform", "tfv5_uid": uid,
                "tfv5_username": username}

    probe = client.status(instance, iss, user_id)
    if probe is not None:
        result = client.platform_bind(instance, iss=iss, sub=user_id,
                                      identifier=identifier, password=password)
        if result.get("success") is not True:
            raise _map_error(result.get("error", "bind_failed"))
        uid = int(result.get("uid") or 0)
        username = str(result.get("username") or identifier)
        _upsert_connection(db, user_id, instance, uid, username, "platform", None,
                           refresh_bound_at=touch)
        return {"ok": True, "channel": "platform", "tfv5_uid": uid,
                "tfv5_username": username}

    # 2) 降级：旧链路
    try:
        login = client.login(instance, identifier=identifier, password=password)
    except Tfv5Error as exc:
        raise BindError(exc.code, str(exc)) from exc
    uid = int(login["uid"])
    token = login["token"]
    ext = _external_token(keystore_of(), settings, instance, user_id, uid)
    try:
        client.external_bind(instance, token=token, external_token=ext)
    except Tfv5Error as exc:
        raise BindError(exc.code, str(exc)) from exc

    sealed = None
    refresh = login.get("refresh_token")
    if isinstance(refresh, str) and refresh:
        sealed = envelope.seal(settings.master_key, refresh)

    username = identifier
    info = client.username_lookup(instance, identifier) if not identifier.strip().isdigit() else None
    if info and info.get("username"):
        username = str(info["username"])
    _upsert_connection(db, user_id, instance, uid, username, "legacy", sealed,
                       refresh_bound_at=touch)
    return {"ok": True, "channel": "legacy", "tfv5_uid": uid, "tfv5_username": username}


def _map_error(code: str) -> BindError:
    # TFV5 在 detail_error=true 时会把内部错误键规范化成大写对外码
    # （error_codes.normalize_error），所以两种写法都要认。
    mapping = {
        "auth_failed": ("tfv5_bad_credentials", "TouchFish 账号或密码不正确"),
        "AUTH_FAILED": ("tfv5_bad_credentials", "TouchFish 账号或密码不正确"),
        "AUTH_INVALID_PASSWORD": ("tfv5_bad_credentials", "TouchFish 账号或密码不正确"),
        "user_banned": ("tfv5_banned", "该 TouchFish 账号已被封禁"),
        "RESOURCE_USER_BANNED": ("tfv5_banned", "该 TouchFish 账号已被封禁"),
        "external_already_linked": ("tfv5_already_linked", "该 TouchFish 账号已关联其他平台账户"),
        "EXTERNAL_ALREADY_LINKED": ("tfv5_already_linked", "该 TouchFish 账号已关联其他平台账户"),
        "platform_not_configured": ("tfv5_not_configured", "TFV5 侧未启用外部认证平台"),
        "PLATFORM_NOT_CONFIGURED": ("tfv5_not_configured", "TFV5 侧未启用外部认证平台"),
        "invalid_request": ("tfv5_invalid_request", "请求参数不被 TFV5 接受"),
        "VALIDATION_INVALID_REQUEST": ("tfv5_invalid_request", "请求参数不被 TFV5 接受"),
    }
    key, message = mapping.get(code, ("tfv5_bind_failed", "绑定失败，请稍后重试"))
    return BindError(key, message)


def _ensure_uid_free(db: Db, instance_id: str, uid: int,
                     ignore_connection_id: str | None = None) -> None:
    """同一个 TFV5 账号在一个实例上只能绑到一个平台账户。

    换绑（UPDATE）和新绑（INSERT）都必须过这一关，否则会直接撞
    UNIQUE(instance_id, tfv5_uid) 抛 IntegrityError，变成 500。
    """
    sql = "SELECT user_id FROM connections WHERE instance_id = ? AND tfv5_uid = ?"
    params: list = [instance_id, uid]
    if ignore_connection_id:
        sql += " AND id <> ?"
        params.append(ignore_connection_id)
    if db.query_one(sql, tuple(params)) is not None:
        raise BindError(
            "tfv5_uid_taken",
            "该 TouchFish 账号已绑定到另一个平台账户，请先在那边解除绑定",
        )


def _upsert_connection(db: Db, user_id: str, instance: Instance, uid: int,
                       username: str, channel: str, sealed: bytes | None,
                       *, refresh_bound_at: bool = True) -> None:
    import secrets
    existing = get_connection(db, user_id, instance.id)
    now = time.time()
    if existing:
        _ensure_uid_free(db, instance.id, uid, ignore_connection_id=existing["id"])
        try:
            if refresh_bound_at:
                db.execute(
                    "UPDATE connections SET tfv5_uid = ?, tfv5_username = ?, iss = ?,"
                    " sub = ?, refresh_token_enc = ?, bind_channel = ?, bound_at = ?,"
                    " last_login_at = ? WHERE id = ?",
                    (uid, username, instance.issuer, user_id, sealed, channel, now,
                     now, existing["id"]),
                )
            else:
                # 登录复用已有绑定：bound_at 应保持首次绑定时间，
                # 只更新 last_login_at，否则前端的"绑定时间"会随每次登录漂移。
                db.execute(
                    "UPDATE connections SET tfv5_uid = ?, tfv5_username = ?, iss = ?,"
                    " sub = ?, refresh_token_enc = ?, bind_channel = ?,"
                    " last_login_at = ? WHERE id = ?",
                    (uid, username, instance.issuer, user_id, sealed, channel,
                     now, existing["id"]),
                )
        except Exception as exc:  # noqa: BLE001 - 并发下的唯一约束
            raise BindError(
                "tfv5_uid_taken",
                "该 TouchFish 账号已绑定到另一个平台账户，请先在那边解除绑定",
            ) from exc
        return

    _ensure_uid_free(db, instance.id, uid)

    try:
        db.execute(
            "INSERT INTO connections (id, user_id, instance_id, tfv5_uid, tfv5_username,"
            " iss, sub, refresh_token_enc, bind_channel, bound_at, last_login_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (secrets.token_hex(12), user_id, instance.id, uid, username,
             instance.issuer, user_id, sealed, channel, now, now),
        )
    except Exception as exc:  # noqa: BLE001 - 并发下的唯一约束
        raise BindError(
            "tfv5_uid_taken",
            "该 TouchFish 账号已绑定到另一个平台账户，请先在那边解除绑定",
        ) from exc


def unbind(db: Db, settings: Settings, user_id: str, instance: Instance) -> None:
    """解除绑定。优先用专用端点；否则用缓存的 refresh token 换会话再解绑。"""
    client = get_client()
    conn = get_connection(db, user_id, instance.id)
    if conn is None:
        return
    iss, sub = conn["iss"], conn["sub"]

    if client.status(instance, iss, sub) is not None:
        client.platform_unbind(instance, iss=iss, sub=sub)
        db.execute("DELETE FROM connections WHERE id = ?", (conn["id"],))
        return

    sealed = conn["refresh_token_enc"]
    if not sealed:
        raise BindError(
            "unbind_requires_password",
            "该服务器版本不支持免密解绑，请重新连接一次后再解除",
        )
    # 用缓存的 refresh token 换一个 TFV5 会话，再调解绑
    from .tfv5 import Tfv5Error as _Err
    refresh = envelope.unseal(settings.master_key, sealed)
    try:
        rotated = client._envelope_call(instance, "/auth/refresh", {  # noqa: SLF001
            "refresh_token": refresh, "detail_error": True,
        })
    except _Err as exc:
        raise BindError("unbind_session_expired", "缓存的 TouchFish 会话已失效，请重新连接后再解除") from exc
    token = rotated.get("token")
    if not token:
        raise BindError("unbind_session_expired", "缓存的 TouchFish 会话已失效，请重新连接后再解除")
    try:
        client._envelope_call(instance, "/auth/external/unbind", {  # noqa: SLF001
            "token": token, "iss": iss, "detail_error": True,
        })
    except _Err as exc:
        raise BindError("unbind_failed", "解除绑定失败，请稍后重试") from exc
    db.execute("DELETE FROM connections WHERE id = ?", (conn["id"],))


# KeyStore 在 main 启动时注入，避免循环依赖
_keystore: KeyStore | None = None


def attach_keystore(keystore: KeyStore) -> None:
    global _keystore
    _keystore = keystore


def keystore_of() -> KeyStore:
    if _keystore is None:  # pragma: no cover
        raise BindError("keystore_uninitialized", "密钥环未初始化")
    return _keystore


def external_token_for(db: Db, settings: Settings, user_id: str,
                       instance: Instance) -> str:
    from . import site as site_service

    conn = get_connection(db, user_id, instance.id)
    uid = int(conn["tfv5_uid"]) if conn else None
    ttl = int(site_service.get_value(db, settings, "token_ttl") or settings.token_ttl)
    return _external_token(keystore_of(), settings, instance, user_id, uid, ttl)

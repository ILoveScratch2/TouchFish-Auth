"""TFV5 账户绑定。"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..deps import api_error, client_ip, current_user, throttle_error, user_agent
from ..runtime import get as get_runtime
from ..security.sessions import create_session
from ..services import binding as binding_service
from ..services import gate
from ..services import instances as instances_repo
from ..services import site
from ..services import users as users_service
from ..services.registration import registration_allowed
from ..services.tfv5 import Tfv5Error, get_client

router = APIRouter()

SESSION_COOKIE_NAME = "tf_session"
CSRF_COOKIE_NAME = "tf_csrf"


class BindBody(BaseModel):
    identifier: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    instance_id: str | None = None
    captcha_token: str | None = None


@router.get("/api/instances")
def list_instances():
    runtime = get_runtime()
    items = [instances_repo.detail(runtime.db, inst)
             for inst in instances_repo.list_instances(runtime.db)]
    return JSONResponse({"instances": items})


@router.get("/api/connections")
def list_connections(request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")
    return JSONResponse({"connections": binding_service.list_connections(runtime.db, user["user_id"])})


@router.post("/api/connections/bind")
def bind(body: BindBody, request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")

    instance = instances_repo.get_instance(runtime.db, body.instance_id)
    if instance is None:
        return api_error(400, "no_instance", "尚未配置 TouchFish 服务器")

    try:
        result = binding_service.bind(runtime.db, runtime.settings, user["user_id"],
                                      instance, body.identifier, body.password)
    except binding_service.BindError as exc:
        runtime.db.audit("connection.bind_failed", user["user_id"],
                         client_ip(request), user_agent(request), detail=exc.code)
        status = 401 if exc.code == "tfv5_bad_credentials" else 409
        return api_error(status, exc.code, exc.message)
    except Tfv5Error as exc:
        return api_error(502, exc.code, str(exc))

    runtime.db.audit("connection.bind", user["user_id"], client_ip(request),
                     user_agent(request),
                     detail=f"{instance.id}:{result.get('tfv5_uid')}:{result.get('channel')}")
    return JSONResponse({"connection": result})


@router.post("/api/connections/tfv5-login")
def tfv5_login(body: BindBody, request: Request):
    """未登录状态下直接用 TFV5 凭据登录：已绑定则登录，未绑定则按策略决定是否开通。"""
    runtime = get_runtime()
    instance = instances_repo.get_instance(runtime.db, body.instance_id)
    if instance is None:
        return api_error(400, "no_instance", "尚未配置 TouchFish 服务器")

    values = site.all_values(runtime.db, runtime.settings)

    # 这同样是一次登录
    if values["captcha_on_login"]:
        failed = gate.check_captcha(
            runtime.db, values, body.captcha_token,
            ip=client_ip(request), ua=user_agent(request),
        )
        if failed is not None:
            return api_error(400, "captcha_failed", f"人机验证未通过：{failed.message}")

    client = get_client()
    probe = client.status(instance, runtime.settings.issuer, "probe")
    # 用真正的 sub 探测?useless（会返回 linked:false），这里只判断端点是否存在
    endpoint_available = probe is not None

    ip = client_ip(request)
    wait = gate.login_blocked(values, ip, body.identifier)
    if wait:
        runtime.db.audit("connection.tfv5_login_throttled", None, ip,
                         user_agent(request), detail=body.identifier[:32])
        return throttle_error(wait)

    if not endpoint_available:
        return _tfv5_login_legacy(runtime, request, instance, body, values, ip)

    # 专用端点可用：先按 (instance, tfv5_uid) 找已有连接
    existing = _find_connection_by_tfv5(runtime.db, instance.id, body.identifier, client, instance)
    if existing is not None:
        conn, tfv5_uid = existing
        # 已绑定分支同样要验密码。
        # 用 platform_bind 做验密入口是安全的：它先 verify_user 再判断映射，
        # 当 (iss, sub) 已指向同一个 uid 时幂等返回 success，且不建会话、不发 token
        try:
            # 入口已经探过 status
            binding_service.bind(runtime.db, runtime.settings, conn["user_id"],
                                 instance, body.identifier, body.password,
                                 assume_platform=True, login_reuse=True)
        except binding_service.BindError as exc:
            gate.login_failed(values, ip, body.identifier)
            runtime.db.audit("connection.tfv5_login_failed", conn["user_id"],
                             ip, user_agent(request), detail=exc.code)
            status = 401 if exc.code in ("tfv5_bad_credentials", "tfv5_banned") else 409
            return api_error(status, exc.code, exc.message)
        except Tfv5Error as exc:
            return api_error(502, exc.code, str(exc))
        gate.login_succeeded(ip, body.identifier)
        return _login_existing(runtime, request, conn["user_id"], tfv5_uid)

    # 未绑定
    allowed, reason = registration_allowed(runtime.db, runtime.settings, instance)
    if not allowed:
        return api_error(403, "register_disabled", reason)
    if not values["tfv5_login_auto_signup"]:
        return api_error(
            409, "auto_signup_disabled",
            "该站点不允许用 TouchFish 凭据直接开通账户，请先用平台账号登录后在账户页绑定",
        )

    new_id = secrets.token_hex(16)
    try:
        result = binding_service.bind(runtime.db, runtime.settings, new_id,
                                      instance, body.identifier, body.password,
                                      assume_platform=True)
    except binding_service.BindError as exc:
        gate.login_failed(values, ip, body.identifier)
        status = 401 if exc.code == "tfv5_bad_credentials" else 409
        return api_error(status, exc.code, exc.message)

    username = users_service.unique_username(runtime.db, str(result.get("tfv5_username") or "tf_user"))
    error = users_service.create_with_id(runtime.db, new_id, username)
    if error:
        # 回滚绑定，避免留下孤儿映射
        try:
            binding_service.unbind(runtime.db, runtime.settings, new_id, instance)
        except Exception:  # noqa: BLE001
            pass
        return api_error(409, "create_failed", error)

    runtime.db.audit("user.tfv5_signup", new_id, ip, user_agent(request),
                     detail=instance.id)
    gate.login_succeeded(ip, body.identifier)
    return _login_existing(runtime, request, new_id, int(result.get("tfv5_uid") or 0))


def _find_connection_by_tfv5(db, instance_id: str, identifier: str, client, instance):
    try:
        tfv5_uid = client.resolve_uid(instance, identifier)
    except Tfv5Error:
        return None
    row = db.query_one(
        "SELECT * FROM connections WHERE instance_id = ? AND tfv5_uid = ?",
        (instance_id, tfv5_uid),
    )
    return (row, tfv5_uid) if row else None


def _login_existing(runtime, request: Request, user_id: str, tfv5_uid: int) -> JSONResponse:
    row = users_service.get(runtime.db, user_id)
    if row is None:
        return api_error(404, "user_not_found", "账户不存在")
    sid, csrf = create_session(runtime.db, user_id, runtime.settings.session_ttl,
                               ip=client_ip(request), user_agent=user_agent(request))
    response = JSONResponse({"user": users_service.public_view(row), "tfv5_uid": tfv5_uid})
    secure = runtime.settings.cookie_secure and request.url.scheme == "https"
    response.set_cookie(SESSION_COOKIE_NAME, sid, max_age=runtime.settings.session_ttl,
                        httponly=True, secure=secure, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE_NAME, csrf, max_age=runtime.settings.session_ttl,
                        httponly=False, secure=secure, samesite="lax", path="/")
    runtime.db.audit("user.tfv5_login", user_id, client_ip(request), user_agent(request),
                     detail=str(tfv5_uid))
    return response


def _tfv5_login_legacy(runtime, request: Request, instance, body: BindBody,
                       values: dict, ip: str) -> JSONResponse:
    """旧版 TFV5：没有专用端点，只能先 login 拿 uid 再判断是否已绑定
    """
    client = get_client()
    try:
        login = client.login(instance, identifier=body.identifier, password=body.password)
    except Tfv5Error as exc:
        gate.login_failed(values, ip, body.identifier)
        runtime.db.audit("connection.tfv5_login_failed", None, ip,
                         user_agent(request), detail=exc.code)
        return api_error(401, exc.code, str(exc))
    gate.login_succeeded(ip, body.identifier)
    tfv5_uid = int(login["uid"])
    row = runtime.db.query_one(
        "SELECT * FROM connections WHERE instance_id = ? AND tfv5_uid = ?",
        (instance.id, tfv5_uid),
    )
    if row is not None:
        return _login_existing(runtime, request, row["user_id"], tfv5_uid)
    return api_error(
        409, "need_signin_first",
        "该 TouchFish 账号尚未关联本平台账户，请先用平台账号登录后在账户页完成绑定",
    )


@router.delete("/api/connections/{instance_id}")
def unbind(instance_id: str, request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")
    instance = instances_repo.get_instance(runtime.db, instance_id)
    if instance is None:
        return api_error(404, "instance_not_found", "实例不存在")
    try:
        binding_service.unbind(runtime.db, runtime.settings, user["user_id"], instance)
    except binding_service.BindError as exc:
        return api_error(409, exc.code, exc.message)
    except Tfv5Error as exc:
        return api_error(502, exc.code, str(exc))
    runtime.db.audit("connection.unbind", user["user_id"], client_ip(request),
                     user_agent(request), detail=instance.id)
    return JSONResponse({"ok": True})

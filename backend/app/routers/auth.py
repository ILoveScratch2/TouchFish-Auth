"""平台账户、会话与站点公开配置。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..deps import api_error, client_ip, current_user, throttle_error, user_agent
from ..runtime import get as get_runtime
from ..security.passwords import verify_password
from ..security.sessions import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    create_session,
    list_sessions,
    revoke_all_except,
    revoke_session,
)
from ..services import gate
from ..services import instances as instances_repo
from ..services import mailer, site, users as users_service, verification
from ..services.registration import registration_allowed

router = APIRouter()


class RegisterBody(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    email: str | None = None
    captcha_token: str | None = None


class LoginBody(BaseModel):
    identifier: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    captcha_token: str | None = None


class PasswordBody(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=8, max_length=128)


class VerifyBody(BaseModel):
    verification_id: str = Field(min_length=8, max_length=64)
    code: str = Field(min_length=4, max_length=12)


class ResendBody(BaseModel):
    identifier: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def _mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    keep = local[:2]
    return f"{keep}{'*' * max(1, len(local) - 2)}@{domain}"


def _set_auth_cookies(response: JSONResponse, request: Request, sid: str, csrf: str) -> None:
    runtime = get_runtime()
    secure = runtime.settings.cookie_secure and request.url.scheme == "https"
    max_age = runtime.settings.session_ttl
    response.set_cookie(SESSION_COOKIE, sid, max_age=max_age, httponly=True,
                        secure=secure, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False,
                        secure=secure, samesite="lax", path="/")


def _clear_auth_cookies(response: JSONResponse) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _issue_session(request: Request, user_id: str, payload: dict) -> JSONResponse:
    runtime = get_runtime()
    sid, csrf = create_session(runtime.db, user_id, runtime.settings.session_ttl,
                               ip=client_ip(request), user_agent=user_agent(request))
    response = JSONResponse(payload)
    _set_auth_cookies(response, request, sid, csrf)
    return response


def _verify_captcha(values: dict, token: str | None, request: Request) -> JSONResponse | None:
    result = gate.check_captcha(
        get_runtime().db, values, token,
        ip=client_ip(request), ua=user_agent(request),
    )
    if result is None:
        return None
    return api_error(400, "captcha_failed", f"人机验证未通过：{result.message}")


@router.get("/api/site")
def public_site() -> JSONResponse:
    """未登录页面需要的公开配置（站点名、公告、验证码、邮箱验证开关）。"""
    runtime = get_runtime()
    instance = instances_repo.get_instance(runtime.db, None)
    allowed, reason = registration_allowed(runtime.db, runtime.settings, instance)
    payload = site.public_config(runtime.db, runtime.settings)
    payload["registration"] = {"allowed": allowed, "reason": reason}
    payload["instance"] = instances_repo.detail(runtime.db, instance) if instance else None
    return JSONResponse(payload)


@router.get("/api/auth/registration")
def registration_status() -> JSONResponse:
    runtime = get_runtime()
    instance = instances_repo.get_instance(runtime.db, None)
    allowed, reason = registration_allowed(runtime.db, runtime.settings, instance)
    return JSONResponse({
        "allowed": allowed,
        "reason": reason,
        "mode": site.get_value(runtime.db, runtime.settings, "registration_mode"),
    })


def _send_code(request: Request, user_id: str, email: str) -> tuple[str | None, JSONResponse | None]:
    runtime = get_runtime()
    values = site.all_values(runtime.db, runtime.settings)
    row_id, code = verification.issue(runtime.db, user_id, email)
    ok, error = mailer.send(
        values, email,
        f"{values['site_name']} 验证码",
        mailer.verification_body(str(values["site_name"]), code),
        dev_mail=runtime.settings.dev_mail,
    )
    if not ok:
        runtime.db.audit("mail.failed", user_id, client_ip(request),
                         user_agent(request), detail=error)
        return None, api_error(502, "mail_failed", error)
    runtime.db.audit("mail.sent", user_id, client_ip(request), user_agent(request),
                     detail=_mask_email(email))
    return row_id, None


@router.post("/api/auth/register")
def register(body: RegisterBody, request: Request):
    runtime = get_runtime()
    db, settings = runtime.db, runtime.settings
    values = site.all_values(db, settings)

    instance = instances_repo.get_instance(db, None)
    allowed, reason = registration_allowed(db, settings, instance)
    if not allowed:
        return api_error(403, "register_disabled", reason)

    if values["captcha_enabled"]:
        failed = _verify_captcha(values, body.captcha_token, request)
        if failed:
            return failed

    needs_email = bool(values["email_verification"])
    if needs_email and not (body.email or "").strip():
        return api_error(400, "email_required", "该站点要求填写邮箱以完成验证")

    user_id, error = users_service.create(
        db, body.username, body.password, body.email,
        status="pending" if needs_email else "active",
    )
    if user_id is None:
        return api_error(400, "register_failed", error)

    db.audit("user.register", user_id, client_ip(request), user_agent(request),
             detail="pending" if needs_email else "active")

    if needs_email:
        row_id, failed = _send_code(request, user_id, (body.email or "").strip())
        if failed:
            return failed
        return JSONResponse({
            "pending_verification": True,
            "verification_id": row_id,
            "email": _mask_email((body.email or "").strip()),
        }, status_code=202)

    row = users_service.get(db, user_id)
    return _issue_session(request, user_id, {"user": users_service.public_view(row)})


@router.post("/api/auth/verify-email")
def verify_email(body: VerifyBody, request: Request):
    runtime = get_runtime()
    db = runtime.db
    user_id = verification.verify_by_id(db, body.verification_id, body.code)
    if user_id is None:
        db.audit("user.verify_failed", None, client_ip(request), user_agent(request),
                 detail=body.verification_id[:8])
        return api_error(400, "code_invalid", "验证码不正确或已过期")

    users_service.activate(db, user_id)
    row = users_service.get(db, user_id)
    if row is None:
        return api_error(404, "user_not_found", "账户不存在")
    db.audit("user.verified", user_id, client_ip(request), user_agent(request))
    return _issue_session(request, user_id, {"user": users_service.public_view(row)})


@router.post("/api/auth/resend-verification")
def resend_verification(body: ResendBody, request: Request):
    runtime = get_runtime()
    db, settings = runtime.db, runtime.settings
    row = users_service.find_by_login(db, body.identifier)
    if row is None or not verify_password(row["password_hash"], body.password):
        return api_error(401, "auth_failed", "账号或密码不正确")
    if row["status"] != "pending":
        return api_error(409, "not_pending", "该账户无需邮箱验证")

    email = row["email"] or verification.pending_email(db, row["id"])
    if not email:
        return api_error(400, "no_email", "该账户没有可用的邮箱地址")

    row_id, failed = _send_code(request, row["id"], email)
    if failed:
        return failed
    return JSONResponse({
        "pending_verification": True,
        "verification_id": row_id,
        "email": _mask_email(email),
    })


@router.post("/api/auth/login")
def login(body: LoginBody, request: Request):
    runtime = get_runtime()
    db, settings = runtime.db, runtime.settings
    values = site.all_values(db, settings)

    if values["captcha_on_login"]:
        failed = _verify_captcha(values, body.captcha_token, request)
        if failed:
            return failed

    ip = client_ip(request)
    wait = gate.login_blocked(values, ip, body.identifier)
    if wait:
        runtime.db.audit("user.login_throttled", None, ip, user_agent(request),
                         detail=body.identifier[:32])
        return throttle_error(wait)

    row, error = users_service.verify_login(db, body.identifier, body.password)
    if row is None:
        status = 403 if error == "account_suspended" else 401
        message = "该账户已被停用" if error == "account_suspended" else "账号或密码不正确"
        gate.login_failed(values, ip, body.identifier)
        db.audit("user.login_failed", None, ip, user_agent(request), detail=error)
        return api_error(status, error, message)

    if row["status"] == "pending":
        return api_error(403, "email_unverified", "该账户尚未完成邮箱验证")

    gate.login_succeeded(ip, body.identifier)
    db.audit("user.login", row["id"], ip, user_agent(request))
    return _issue_session(request, row["id"], {"user": users_service.public_view(row)})


@router.post("/api/auth/logout")
def logout(request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user:
        revoke_session(runtime.db, user["session_id"], user["user_id"])
    response = JSONResponse({"ok": True})
    _clear_auth_cookies(response)
    return response


@router.get("/api/auth/me")
def me(request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return JSONResponse({"user": None})
    row = users_service.get(runtime.db, user["user_id"])
    return JSONResponse({"user": users_service.public_view(row)})


@router.post("/api/auth/password")
def change_password(body: PasswordBody, request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")

    row = users_service.get(runtime.db, user["user_id"])
    if row["password_hash"]:
        if not body.current_password or not verify_password(row["password_hash"],
                                                            body.current_password):
            return api_error(400, "bad_password", "当前密码不正确")

    users_service.set_password(runtime.db, user["user_id"], body.new_password)
    revoke_all_except(runtime.db, user["user_id"], user["session_id"])
    runtime.db.audit("user.password_changed", user["user_id"],
                     client_ip(request), user_agent(request))
    return JSONResponse({"ok": True})


@router.get("/api/auth/sessions")
def sessions(request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")
    items = list_sessions(runtime.db, user["user_id"])
    for item in items:
        item["current"] = item["id"] == user["session_id"]
    return JSONResponse({"sessions": items})


@router.delete("/api/auth/sessions/{session_id}")
def revoke(session_id: str, request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")
    if not revoke_session(runtime.db, session_id, user["user_id"]):
        return api_error(404, "session_not_found", "会话不存在或已失效")
    return JSONResponse({"ok": True})

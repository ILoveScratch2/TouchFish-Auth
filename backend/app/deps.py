"""请求依赖。"""
from __future__ import annotations

import hmac
from typing import Any
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

from .runtime import get as get_runtime
from .security.sessions import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    resolve_session,
    touch_session,
)

CSRF_EXEMPT = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/ticket",   # 原生客户端调用，无浏览器 cookie
    # 邮箱验证在建立会话之前发生，此时还没有 csrf cookie
    "/api/auth/verify-email",
    "/api/auth/resend-verification",
    # 匿名场景的"用 TFV5 凭据登录"：它靠凭据认证而非 cookie 会话，
    # 且主场景就是首次访问（此时必然没有 csrf cookie）。不加豁免该功能永远 403
    "/api/connections/tfv5-login",
    "/api/dev/throttle/reset",  # 仅 AUTH_DEV_MAIL=1 时存在
    "/api/health",
}


def origin_allowed(request: Request) -> bool:
    """同源判定，用于保护 no CSRF endpoint 
    """
    origin = request.headers.get("origin")
    if not origin:
        return True  # 非浏览器发起（原生客户端 / curl / 服务端调用）
    if origin == "null":
        return False  # 沙箱 iframe、file:// 之类，一律拒绝
    try:
        origin_netloc = urlparse(origin).netloc.lower()
    except ValueError:
        return False
    if not origin_netloc:
        return False

    try:
        extra = {item.lower() for item in get_runtime().settings.allowed_origins}
    except RuntimeError:
        extra = set()
    if origin_netloc in extra or origin.lower() in extra:
        return True

    host = (request.headers.get("host") or "").lower()
    if not host:
        return False
    # 同源必须同协议：http://auth 发起的请求打到 https://auth 会被判跨站，
    # 避免在 http 侧被劫持时绕过同源闸门（实际风险低，但加严无成本）。
    try:
        origin_scheme = urlparse(origin).scheme.lower()
    except ValueError:
        return False
    return origin_netloc == host and origin_scheme == request.url.scheme


def api_error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def throttle_error(wait_seconds: int) -> JSONResponse:
    """429 + Retry-After：让客户端知道多久后可以重试，而不是盲猜。"""
    return JSONResponse(
        status_code=429,
        content={"error": {
            "code": "too_many_attempts",
            "message": f"尝试次数过多，请 {wait_seconds} 秒后再试",
            "retry_after": wait_seconds,
        }},
        headers={"Retry-After": str(wait_seconds)},
    )


def current_user(request: Request) -> dict[str, Any] | None:
    runtime = get_runtime()
    sid = request.cookies.get(SESSION_COOKIE)
    user = resolve_session(runtime.db, sid)
    if user is None:
        return None
    touch_session(runtime.db, user["session_id"])
    return user


def require_user(request: Request) -> dict[str, Any] | JSONResponse:
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")
    return user


def csrf_ok(request: Request) -> bool:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    if request.url.path in CSRF_EXEMPT:
        # 免 token，但浏览器跨站请求仍需同源
        return origin_allowed(request)
    cookie = request.cookies.get(CSRF_COOKIE) or ""
    header = request.headers.get(CSRF_HEADER) or ""
    if not cookie or not header:
        return False
    return hmac.compare_digest(cookie, header)


def client_ip(request: Request) -> str:
    """真实客户端 IP。

    反代场景请用 uvicorn 的 `--proxy-headers --forwarded-allow-ips=<代理地址>`
    让 `request.client` 自己变成真实 IP
    只有在无法使用该机制时才开
    `AUTH_TRUST_PROXY=1` 兜底。
    """
    try:
        trusted = get_runtime().settings.trust_proxy
    except RuntimeError:
        trusted = False
    if trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:256]

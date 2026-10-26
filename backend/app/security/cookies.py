from __future__ import annotations

from fastapi import Request
from fastapi.responses import Response

from ..runtime import get as get_runtime
from .sessions import CSRF_COOKIE, SESSION_COOKIE


def set_auth_cookies(response: Response, request: Request, sid: str, csrf: str) -> None:
    runtime = get_runtime()
    secure = runtime.settings.cookie_secure and request.url.scheme == "https"
    max_age = runtime.settings.session_ttl
    response.set_cookie(SESSION_COOKIE, sid, max_age=max_age, httponly=True,
                        secure=secure, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False,
                        secure=secure, samesite="lax", path="/")


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")

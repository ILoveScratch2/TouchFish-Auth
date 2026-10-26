"""第三方 OAuth 登录与账号绑定。

`/start` 与 `/callback` 是浏览器导航!!!!!!!!
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..deps import api_error, client_ip, current_user, user_agent
from ..runtime import get as get_runtime
from ..security.cookies import set_auth_cookies
from ..security.sessions import create_session
from ..services import instances as instances_repo
from ..services import oauth
from ..services import users as users_service
from ..services.registration import registration_allowed

router = APIRouter()


def _login_redirect(code: str) -> RedirectResponse:
    return RedirectResponse(f"/login?oauth_error={quote(code)}", status_code=302)


def _safe_redirect(target: str) -> str:
    """TF Auth 内部跳转
    """
    if not isinstance(target, str) or not target.startswith("/"):
        return "/account"
    if target.startswith("//") or "\\" in target:
        return "/account"
    if "\r" in target or "\n" in target:
        return "/account"
    return target


def _with_flag(target: str, key: str, value: str) -> str:
    """+参数
    不要直接拼接不然会炸！
    """
    head, sep, query = target.partition("?")
    extra = urlencode({key: value})
    return f"{head}?{query}&{extra}" if sep and query else f"{head}?{extra}"


def _callback_uri(request: Request, provider_id: str) -> str:
    base = get_runtime().settings.base_url
    return f"{base}/api/auth/oauth/{provider_id}/callback"


@router.get("/api/auth/oauth/{provider_id}/start")
def oauth_start(provider_id: str, request: Request, redirect: str = "/account",
                bind: int = 0):
    """跳转 provider auth
    """
    runtime = get_runtime()
    cfg = oauth.resolve(runtime.db, runtime.settings, provider_id)
    if cfg is None:
        return _login_redirect("provider_unavailable")

    mode, user_id, target = "login", "", _safe_redirect(redirect)
    if bind:
        user = current_user(request)
        if user is None:
            # 未登录绑定
            return _login_redirect("bind_requires_login")
        mode, user_id = "bind", user["user_id"]
        target = "/account"

    state = oauth.make_state(runtime.settings, provider_id, target, mode, user_id)
    destination = oauth.authorize_url(cfg, _callback_uri(request, provider_id), state)
    return RedirectResponse(destination, status_code=302)


@router.get("/api/auth/oauth/{provider_id}/callback")
def oauth_callback(provider_id: str, request: Request,
                   code: str = "", state: str = "", error: str = ""):
    runtime = get_runtime()
    db, settings = runtime.db, runtime.settings
    ip, ua = client_ip(request), user_agent(request)

    if error:
        db.audit("oauth.denied", None, ip, ua, detail=f"{provider_id}:{error}"[:120])
        return _login_redirect("access_denied")

    parsed = oauth.parse_state(settings, state)
    if parsed is None or parsed[0] != provider_id:
        db.audit("oauth.bad_state", None, ip, ua, detail=provider_id)
        return _login_redirect("state_invalid")
    _, redirect_to, mode, bind_uid = parsed
    redirect_to = _safe_redirect(redirect_to)

    cfg = oauth.resolve(db, settings, provider_id)
    if cfg is None:
        return _login_redirect("provider_unavailable")

    try:
        profile = oauth.fetch_profile(cfg, code, _callback_uri(request, provider_id))
        if mode == "bind":
            user = current_user(request)
            if user is None or user["user_id"] != bind_uid:
                db.audit("oauth.bind_session_mismatch", None, ip, ua, detail=provider_id)
                return RedirectResponse(
                    "/login?oauth_error=" + quote("bind_session_mismatch"),
                    status_code=302)
            oauth.link_account(db, bind_uid, profile)
            db.audit("oauth.bind", bind_uid, ip, ua,
                     detail=f"{provider_id}:{profile['login'][:32]}")
            return RedirectResponse(
                _with_flag(redirect_to, "oauth", "linked"), status_code=302)

        user_id = _resolve_user(db, settings, profile)
    except oauth.OAuthError as exc:
        db.audit("oauth.failed", None, ip, ua,
                 detail=f"{provider_id}:{exc.code}:{exc.message}"[:200])
        if mode == "bind":
            return RedirectResponse(
                "/account?oauth_error=" + quote(exc.code), status_code=302)
        return _login_redirect(exc.code)

    sid, csrf = create_session(db, user_id, settings.session_ttl, ip=ip, user_agent=ua)
    db.audit("oauth.login", user_id, ip, ua,
             detail=f"{provider_id}:{profile['login'][:32]}")

    response = RedirectResponse(_with_flag(redirect_to, "oauth", "ok"), status_code=302)
    set_auth_cookies(response, request, sid, csrf)
    return response


def _resolve_user(db, settings, profile: dict) -> str:
    linked = db.query_one(
        "SELECT user_id FROM oauth_accounts WHERE provider = ? AND provider_uid = ?",
        (profile["provider"], profile["provider_uid"]),
    )
    if linked is not None:
        db.execute(
            "UPDATE oauth_accounts SET email = ?, login = ?, avatar_url = ?"
            " WHERE provider = ? AND provider_uid = ?",
            (profile["email"] or None, profile["login"] or None,
             profile["avatar_url"] or None,
             profile["provider"], profile["provider_uid"]),
        )
        return linked["user_id"]

    if profile["email_verified"] and profile["email"]:
        existing = db.query_one(
            "SELECT id FROM users WHERE email_key = ?", (profile["email"],))
        if existing is not None:
            _link_account(db, existing["id"], profile)
            return existing["id"]

    instance = instances_repo.get_instance(db, None)
    allowed, reason = registration_allowed(db, settings, instance)
    if not allowed:
        raise oauth.OAuthError("register_disabled", reason)

    username = users_service.unique_username(
        db, profile["login"] or f"{profile['provider']}_user")
    user_id, message = users_service.create(
        db, username, None, profile["email"] or None, status="active")
    if user_id is None:
        raise oauth.OAuthError("create_failed", message)
    _link_account(db, user_id, profile)
    return user_id


def _link_account(db, user_id: str, profile: dict) -> None:
    try:
        oauth.link_account(db, user_id, profile)
    except oauth.OAuthError as exc:
        if exc.code == "provider_already_bound":
            raise oauth.OAuthError(
                "already_linked", "该平台账号已绑定另一个平台账号") from exc
        raise


@router.get("/api/auth/oauth/accounts")
def oauth_accounts(request: Request):
    """当前用户可绑定的平台状态
    """
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")

    linked = oauth.list_accounts(runtime.db, user["user_id"])
    by_provider = {row["provider"]: row for row in linked}

    items = []
    for provider in oauth.public(runtime.db, runtime.settings):
        row = by_provider.get(provider["id"])
        items.append({
            "id": provider["id"],
            "name": provider["name"],
            "linked": row is not None,
            "login": row["login"] if row else None,
        })

    known = {item["id"] for item in items}
    for row in linked:
        if row["provider"] not in known:
            items.append({
                "id": row["provider"],
                "name": row["provider"],
                "linked": True,
                "login": row["login"],
                "orphan": True,
            })

    record = runtime.db.query_one(
        "SELECT password_hash FROM users WHERE id = ?", (user["user_id"],))
    return JSONResponse({
        "providers": items,
        "has_password": bool(record and record["password_hash"]),
    })


@router.delete("/api/auth/oauth/accounts/{provider_id}")
def oauth_unlink(provider_id: str, request: Request):
    """解绑"""
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")

    db = runtime.db
    record = db.query_one(
        "SELECT password_hash FROM users WHERE id = ?", (user["user_id"],))
    has_password = bool(record and record["password_hash"])
    if not has_password and len(oauth.list_accounts(db, user["user_id"])) <= 1:
        return api_error(409, "last_login_method",
                         "这是当前唯一的登录方式，请先设置密码再解绑")

    try:
        oauth.unlink_account(db, user["user_id"], provider_id)
    except oauth.OAuthError as exc:
        return api_error(404, exc.code, exc.message)

    db.audit("oauth.unlink", user["user_id"], client_ip(request),
             user_agent(request), detail=provider_id)
    return JSONResponse({"ok": True})

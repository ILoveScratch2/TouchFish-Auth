"""OAuth2 / OIDC 授权
"""
from __future__ import annotations

import base64
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..deps import api_error, client_ip, current_user, user_agent
from ..runtime import get as get_runtime
from ..services import oidc

router = APIRouter()


def _oauth_error(code: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": code, "error_description": description},
        status_code=status,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _append_query(uri: str, params: dict[str, str | None]) -> str:
    """在回调地址上追加参数"""
    parts = urlsplit(uri)
    merged = parse_qs(parts.query, keep_blank_values=True)
    for key, value in params.items():
        if value is not None:
            merged[key] = [value]
    pairs = [(key, item) for key, items in merged.items() for item in items]
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(pairs, quote_via=quote), parts.fragment))


def _basic_credentials(request: Request) -> tuple[str, str] | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return None
    try:
        raw = base64.b64decode(header[6:].strip()).decode("utf-8")
    except Exception:  # noqa: BLE001
        return None
    client_id, _, secret = raw.partition(":")
    # RFC 6749 2.3.1
    # form-urlencoded 编码后 Basic
    return unquote(client_id), unquote(secret)


async def _form(request: Request) -> dict[str, str]:
    """解析 application/x-www-form-urlencoded，不引入 python-multipart。"""
    body = (await request.body()).decode("utf-8", "replace")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items() if values}


class AuthorizeBody(BaseModel):
    client_id: str = Field(max_length=128)
    redirect_uri: str = Field(max_length=512)
    response_type: str = Field(default="code", max_length=32)
    scope: str | None = Field(default=None, max_length=256)
    state: str | None = Field(default=None, max_length=512)
    nonce: str | None = Field(default=None, max_length=256)
    code_challenge: str | None = Field(default=None, max_length=128)
    code_challenge_method: str | None = Field(default=None, max_length=16)
    decision: str = Field(default="allow", max_length=16)


def _check(runtime, body: AuthorizeBody) -> dict:
    return oidc.check_authorize_request(
        runtime.db,
        client_id=body.client_id,
        redirect_uri=body.redirect_uri,
        response_type=body.response_type,
        scope=body.scope,
        code_challenge=body.code_challenge,
        code_challenge_method=body.code_challenge_method,
        state=body.state,
        nonce=body.nonce,
    )


@router.get("/api/oidc/request")
def oidc_request(
    client_id: str = "",
    redirect_uri: str = "",
    response_type: str = "code",
    scope: str = "",
    state: str = "",
    nonce: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
):
    """
    预校验。
    """
    runtime = get_runtime()
    body = AuthorizeBody(
        client_id=client_id, redirect_uri=redirect_uri,
        response_type=response_type, scope=scope or None,
        state=state or None, nonce=nonce or None,
        code_challenge=code_challenge or None,
        code_challenge_method=code_challenge_method or None,
    )
    try:
        request_info = _check(runtime, body)
    except oidc.OidcError as exc:
        return api_error(exc.status, exc.code, exc.message)

    return JSONResponse({
        "client_id": request_info["client_id"],
        "client_name": request_info["client_name"],
        "redirect_uri": request_info["redirect_uri"],
        "scope": request_info["scope"],
        "scopes": oidc.scope_list(request_info["scope"]),
        "state": request_info["state"],
    })


@router.post("/api/oidc/approve")
def oidc_approve(body: AuthorizeBody, request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")

    try:
        request_info = _check(runtime, body)
    except oidc.OidcError as exc:
        return api_error(exc.status, exc.code, exc.message)

    if body.decision != "allow":
        runtime.db.audit("oidc.deny", user["user_id"], client_ip(request),
                         user_agent(request), detail=request_info["client_id"])
        return JSONResponse({"redirect": _append_query(
            request_info["redirect_uri"],
            {"error": "access_denied", "state": request_info["state"]},
        )})

    code = oidc.issue_code(runtime.db, request_info, user["user_id"])
    runtime.db.audit("oidc.authorize", user["user_id"], client_ip(request),
                     user_agent(request),
                     detail=f"{request_info['client_id']}:{request_info['scope']}")
    return JSONResponse({"redirect": _append_query(
        request_info["redirect_uri"],
        {"code": code, "state": request_info["state"]},
    )})



@router.post("/token")
async def token_endpoint(request: Request):
    runtime = get_runtime()
    form = await _form(request)
    grant_type = form.get("grant_type", "")

    if grant_type not in ("authorization_code", "refresh_token"):
        return _oauth_error("unsupported_grant_type",
                            "只支持 authorization_code 与 refresh_token")

    basic = _basic_credentials(request)
    client_id = basic[0] if basic else form.get("client_id", "")
    client_secret = basic[1] if basic else form.get("client_secret", "")
    if not client_id:
        return _oauth_error("invalid_client", "缺少 client_id", 401)

    client = oidc.find_client(runtime.db, client_id)
    if client is None or not client["enabled"]:
        return _oauth_error("invalid_client", "未知或已停用的客户端", 401)
    if client["secret_hash"] is not None:
        if not client_secret or not oidc.verify_client_secret(
                runtime.db, client_id, client_secret):
            return _oauth_error("invalid_client", "client_secret 不正确", 401)

    ip, ua = client_ip(request), user_agent(request)
    try:
        if grant_type == "authorization_code":
            code = form.get("code", "")
            if not code:
                return _oauth_error("invalid_request", "缺少 code")
            redeemed = oidc.redeem_code(
                runtime.db, client_id, code, form.get("redirect_uri", ""),
                form.get("code_verifier"),
            )
            payload = oidc.issue_tokens(
                runtime.db, runtime.keystore, runtime.settings, client_id,
                redeemed["user_id"], redeemed["scope"], redeemed["nonce"],
            )
            runtime.db.audit("oidc.token", redeemed["user_id"], ip, ua,
                             detail=f"{client_id}:{grant_type}")
            return JSONResponse(payload, headers={"Cache-Control": "no-store"})

        refresh_token = form.get("refresh_token", "")
        if not refresh_token:
            return _oauth_error("invalid_request", "缺少 refresh_token")
        payload = oidc.rotate_refresh(
            runtime.db, runtime.keystore, runtime.settings, client_id, refresh_token)
        runtime.db.audit("oidc.refresh", None, ip, ua, detail=client_id)
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})
    except oidc.OidcError as exc:
        return _oauth_error(exc.code, exc.message, 400)


@router.get("/api/userinfo")
def userinfo(request: Request):
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return JSONResponse(
            {"error": "invalid_token", "error_description": "缺少 Bearer 令牌"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="touchfish-auth"'},
        )
    runtime = get_runtime()
    token = header[7:].strip()
    try:
        claims = oidc.userinfo(runtime.db, token)
    except oidc.OidcError as exc:
        return JSONResponse(
            {"error": exc.code, "error_description": exc.message},
            status_code=401,
            headers={"WWW-Authenticate":
                     'Bearer error="invalid_token", realm="touchfish-auth"'},
        )
    return JSONResponse(claims, headers={"Cache-Control": "no-store"})

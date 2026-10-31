from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..deps import api_error, client_ip, user_agent
from ..runtime import get as get_runtime
from ..services import oauth
from .admin import _require_admin

router = APIRouter()


class ProviderBody(BaseModel):
    provider_key: str | None = Field(default=None, max_length=32)
    display_name: str | None = Field(default=None, max_length=48)
    client_id: str | None = Field(default=None, max_length=200)
    # 留空 = 不修改
    client_secret: str | None = Field(default=None, max_length=256)
    authorize_url: str | None = Field(default=None, max_length=256)
    token_url: str | None = Field(default=None, max_length=256)
    userinfo_url: str | None = Field(default=None, max_length=256)
    emails_url: str | None = Field(default=None, max_length=256)
    scope: str | None = Field(default=None, max_length=200)
    token_auth_method: str | None = Field(default=None, max_length=8)
    uid_field: str | None = Field(default=None, max_length=48)
    username_field: str | None = Field(default=None, max_length=48)
    email_field: str | None = Field(default=None, max_length=48)
    allowed_hosts: str | None = Field(default=None, max_length=300)
    enabled: bool | None = None


@router.get("/api/admin/oauth/templates")
def templates(request: Request):
    """新建时的预填模板"""
    _, error = _require_admin(request)
    if error:
        return error
    return JSONResponse({
        "templates": [
            {"key": key, **value} for key, value in oauth.TEMPLATES.items()
        ]
    })


@router.get("/api/admin/oauth/providers")
def list_providers(request: Request):
    runtime = get_runtime()
    _, error = _require_admin(request)
    if error:
        return error
    return JSONResponse({
        "providers": oauth.admin_view(runtime.db, runtime.settings),
        "callback_base": f"{runtime.settings.base_url}/api/auth/oauth",
    })


@router.post("/api/admin/oauth/providers")
def create_provider(request: Request, body: ProviderBody):
    runtime = get_runtime()
    admin, error = _require_admin(request)
    if error:
        return error
    try:
        provider_key = oauth.create(
            runtime.db, runtime.settings, body.model_dump(exclude_none=True))
    except oauth.ProviderError as exc:
        return api_error(400, "invalid_provider", exc.message)
    runtime.db.audit("admin.oauth_provider_created", admin["user_id"],
                     client_ip(request), user_agent(request), detail=provider_key)
    return JSONResponse({"ok": True, "provider_key": provider_key}, status_code=201)


@router.put("/api/admin/oauth/providers/{provider_id}")
def update_provider(provider_id: str, request: Request, body: ProviderBody):
    runtime = get_runtime()
    admin, error = _require_admin(request)
    if error:
        return error
    try:
        provider_key = oauth.update(
            runtime.db, runtime.settings, provider_id,
            body.model_dump(exclude_none=True))
    except oauth.ProviderError as exc:
        return api_error(400, "invalid_provider", exc.message)
    runtime.db.audit("admin.oauth_provider_updated", admin["user_id"],
                     client_ip(request), user_agent(request), detail=provider_key)
    return JSONResponse({"ok": True, "provider_key": provider_key})


@router.delete("/api/admin/oauth/providers/{provider_id}")
def delete_provider(provider_id: str, request: Request, force: int = 0):
    runtime = get_runtime()
    admin, error = _require_admin(request)
    if error:
        return error
    try:
        removed = oauth.delete(runtime.db, provider_id, force=bool(force))
    except oauth.ProviderError as exc:
        code = "provider_in_use" if exc.field == "in_use" else "invalid_provider"
        return api_error(400, code, exc.message)
    runtime.db.audit("admin.oauth_provider_deleted", admin["user_id"],
                     client_ip(request), user_agent(request),
                     detail=f"{removed['provider_key']}:{removed['linked_accounts']}")
    return JSONResponse({"ok": True, **removed})

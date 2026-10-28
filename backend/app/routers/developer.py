"""开发者自助：让普通用户创建自己的 OIDC 客户端。

与管理端 `/api/admin/oauth/clients` 的区别只有两处：
  - 只能看/改自己创建的（`owner_id` 归属校验）；
  - 受站点策略 `oauth_apps_self_service` 与 `oauth_apps_max_per_user` 约束。
配额只统计自助创建的应用，管理员创建的不占用户额度。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..deps import api_error, client_ip, current_user, user_agent
from ..runtime import get as get_runtime
from ..services import oidc, site

router = APIRouter()


class AppBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    redirect_uris: list[str] = Field(min_length=1, max_length=20)
    scopes: list[str] = Field(default_factory=list, max_length=10)
    public: bool = False


class AppPatch(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    redirect_uris: list[str] | None = Field(default=None, max_length=20)
    scopes: list[str] | None = Field(default=None, max_length=10)
    enabled: bool | None = None


def _policy(runtime) -> tuple[bool, int]:
    values = site.all_values(runtime.db, runtime.settings)
    return (bool(values["oauth_apps_self_service"]),
            int(values["oauth_apps_max_per_user"]))


def _owned(runtime, client_id: str, user_id: str):
    """取自己的客户端；不存在或属于别人都返回 None（不泄露是否存在）。"""
    row = oidc.find_client(runtime.db, client_id)
    if row is None or row["owner_id"] != user_id:
        return None
    return row


@router.get("/api/developer/apps")
def list_apps(request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")
    self_service, limit = _policy(runtime)
    apps = oidc.list_clients(runtime.db, user["user_id"])
    return JSONResponse({
        "self_service": self_service,
        "max_per_user": limit,
        "used": len(apps),
        "apps": apps,
    })


@router.post("/api/developer/apps")
def create_app(body: AppBody, request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")

    self_service, limit = _policy(runtime)
    if not self_service:
        return api_error(403, "self_service_disabled",
                         "本站未开放自助创建应用，请联系管理员")
    used = len(oidc.list_clients(runtime.db, user["user_id"]))
    if used >= limit:
        return api_error(403, "quota_exceeded",
                         f"最多创建 {limit} 个应用，请先删除不再使用的")

    try:
        client, secret = oidc.create_client(
            runtime.db, body.name, body.redirect_uris, body.scopes,
            body.public, owner_id=user["user_id"])
    except oidc.OidcError as exc:
        return api_error(exc.status, exc.code, exc.message)

    runtime.db.audit("developer.app_create", user["user_id"], client_ip(request),
                     user_agent(request), detail=client["client_id"])
    return JSONResponse({"app": client, "client_secret": secret}, status_code=201)


@router.put("/api/developer/apps/{client_id}")
def update_app(client_id: str, body: AppPatch, request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")
    if _owned(runtime, client_id, user["user_id"]) is None:
        return api_error(404, "app_not_found", "应用不存在")
    try:
        client = oidc.update_client(
            runtime.db, client_id, name=body.name,
            redirect_uris=body.redirect_uris, scopes=body.scopes,
            enabled=body.enabled)
    except oidc.OidcError as exc:
        return api_error(exc.status, exc.code, exc.message)
    return JSONResponse({"app": client})


@router.post("/api/developer/apps/{client_id}/secret")
def rotate_secret(client_id: str, request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")
    if _owned(runtime, client_id, user["user_id"]) is None:
        return api_error(404, "app_not_found", "应用不存在")
    try:
        secret = oidc.rotate_secret(runtime.db, client_id)
    except oidc.OidcError as exc:
        return api_error(exc.status, exc.code, exc.message)
    runtime.db.audit("developer.app_secret", user["user_id"], client_ip(request),
                     user_agent(request), detail=client_id)
    return JSONResponse({"client_secret": secret})


@router.delete("/api/developer/apps/{client_id}")
def delete_app(client_id: str, request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")
    if _owned(runtime, client_id, user["user_id"]) is None:
        return api_error(404, "app_not_found", "应用不存在")
    try:
        oidc.delete_client(runtime.db, client_id)
    except oidc.OidcError as exc:
        return api_error(exc.status, exc.code, exc.message)
    runtime.db.audit("developer.app_delete", user["user_id"], client_ip(request),
                     user_agent(request), detail=client_id)
    return JSONResponse({"ok": True})

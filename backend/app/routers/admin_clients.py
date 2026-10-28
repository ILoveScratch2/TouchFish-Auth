from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..deps import api_error, client_ip, user_agent
from ..runtime import get as get_runtime
from ..services import oidc
from .admin import _require_admin

router = APIRouter()


class ClientBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    redirect_uris: list[str] = Field(min_length=1, max_length=20)
    scopes: list[str] = Field(default_factory=list, max_length=10)
    # True = 公开客户端
    public: bool = False


class ClientPatch(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    redirect_uris: list[str] | None = Field(default=None, max_length=20)
    scopes: list[str] | None = Field(default=None, max_length=10)
    enabled: bool | None = None


@router.get("/api/admin/oauth/clients")
def list_clients(request: Request):
    _, error = _require_admin(request)
    if error:
        return error
    return JSONResponse({"clients": oidc.list_clients(get_runtime().db)})


@router.post("/api/admin/oauth/clients")
def create_client(body: ClientBody, request: Request):
    runtime = get_runtime()
    user, error = _require_admin(request)
    if error:
        return error
    try:
        client, secret = oidc.create_client(
            runtime.db, body.name, body.redirect_uris, body.scopes, body.public)
    except oidc.OidcError as exc:
        return api_error(exc.status, exc.code, exc.message)

    runtime.db.audit("oidc.client_create", user["user_id"], client_ip(request),
                     user_agent(request), detail=client["client_id"])
    # secret 只在这
    return JSONResponse({"client": client, "client_secret": secret}, status_code=201)


@router.put("/api/admin/oauth/clients/{client_id}")
def update_client(client_id: str, body: ClientPatch, request: Request):
    runtime = get_runtime()
    _, error = _require_admin(request)
    if error:
        return error
    try:
        client = oidc.update_client(
            runtime.db, client_id, name=body.name,
            redirect_uris=body.redirect_uris, scopes=body.scopes,
            enabled=body.enabled)
    except oidc.OidcError as exc:
        return api_error(exc.status, exc.code, exc.message)
    return JSONResponse({"client": client})


@router.post("/api/admin/oauth/clients/{client_id}/secret")
def rotate_secret(client_id: str, request: Request):
    runtime = get_runtime()
    _, error = _require_admin(request)
    if error:
        return error
    try:
        secret = oidc.rotate_secret(runtime.db, client_id)
    except oidc.OidcError as exc:
        return api_error(exc.status, exc.code, exc.message)
    return JSONResponse({"client_secret": secret})


@router.delete("/api/admin/oauth/clients/{client_id}")
def delete_client(client_id: str, request: Request):
    runtime = get_runtime()
    user, error = _require_admin(request)
    if error:
        return error
    try:
        oidc.delete_client(runtime.db, client_id)
    except oidc.OidcError as exc:
        return api_error(exc.status, exc.code, exc.message)
    runtime.db.audit("oidc.client_delete", user["user_id"], client_ip(request),
                     user_agent(request), detail=client_id)
    return JSONResponse({"ok": True})

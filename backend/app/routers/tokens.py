"""代授权：一次性 ticket → 短时 external_token。"""
from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..deps import api_error, client_ip, current_user, user_agent
from ..runtime import get as get_runtime
from ..services import binding as binding_service
from ..services import instances as instances_repo
from ..services import site

router = APIRouter()


class CompleteBody(BaseModel):
    client_id: str = Field(default="touchfish", max_length=64)
    state: str | None = Field(default=None, max_length=256)
    target: str | None = Field(default=None, max_length=256)
    instance_id: str | None = Field(default=None, max_length=64)


class TicketBody(BaseModel):
    ticket: str = Field(min_length=8, max_length=128)
    client_id: str = Field(default="touchfish", max_length=64)


@router.post("/api/authorize/complete")
def complete(body: CompleteBody, request: Request):
    """把已登录的浏览器会话换成一次性 ticket
    """
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")

    instance = instances_repo.resolve_target(runtime.db, body.target)
    if instance is None:
        return api_error(400, "no_instance", "尚未配置 TouchFish 服务器")

    conn = binding_service.get_connection(runtime.db, user["user_id"], instance.id)
    if conn is None:
        return api_error(409, "not_linked",
                         "该账户尚未连接这个 TouchFish 服务器，请先完成连接")

    ticket = secrets.token_urlsafe(32)
    now = time.time()
    ttl = int(site.get_value(runtime.db, runtime.settings, "ticket_ttl") or 60)
    runtime.db.execute(
        "INSERT INTO tickets (ticket, user_id, instance_id, client_id, created_at, expires_at)"
        " VALUES (?,?,?,?,?,?)",
        (ticket, user["user_id"], instance.id, body.client_id, now, now + ttl),
    )
    runtime.db.audit("authorize.complete", user["user_id"], client_ip(request),
                     user_agent(request), detail=f"{instance.id}:{body.client_id}")
    return JSONResponse({
        "ticket": ticket,
        "expires_in": ttl,
        "state": body.state,
        "instance_id": instance.id,
    })


@router.post("/api/auth/ticket")
def exchange(body: TicketBody, request: Request):
    """原生客户端调用：一次性 ticket 换 external_token（不依赖浏览器 cookie）。"""
    runtime = get_runtime()

    row = runtime.db.query_one("SELECT * FROM tickets WHERE ticket = ?", (body.ticket,))
    if row is None:
        return api_error(404, "ticket_not_found", "票据无效或已使用")
    if row["consumed_at"] is not None:
        return api_error(409, "ticket_consumed", "票据已使用")
    if float(row["expires_at"]) < time.time():
        return api_error(410, "ticket_expired", "票据已过期，请重新登录")
    if row["client_id"] != body.client_id:
        return api_error(403, "client_mismatch", "票据不属于该客户端")

    consumed = runtime.db.execute(
        "UPDATE tickets SET consumed_at = ? WHERE ticket = ? AND consumed_at IS NULL",
        (time.time(), body.ticket),
    )
    if consumed == 0:
        return api_error(409, "ticket_consumed", "票据已使用")

    instance = instances_repo.get_instance(runtime.db, row["instance_id"])
    if instance is None:
        return api_error(400, "no_instance", "实例已不存在")

    try:
        token = binding_service.external_token_for(runtime.db, runtime.settings,
                                                   row["user_id"], instance)
    except binding_service.BindError as exc:
        return api_error(500, exc.code, exc.message)

    runtime.db.audit("ticket.exchanged", row["user_id"], client_ip(request),
                     user_agent(request), detail=instance.id)
    return JSONResponse({
        "external_token": token,
        "issuer": runtime.settings.issuer,
        "expires_in": int(site.get_value(runtime.db, runtime.settings, "token_ttl") or 300),
        "instance_id": instance.id,
        "tfv5_base_url": instance.base_url,
    })


@router.get("/api/developer/summary")
def developer_summary(request: Request):
    runtime = get_runtime()
    user = current_user(request)
    if user is None:
        return api_error(401, "not_authenticated", "请先登录")

    settings = runtime.settings
    kids = [entry.kid for entry in runtime.keystore.public_entries()]
    return JSONResponse({
        "issuer": settings.issuer,
        "jwks_uri": f"{settings.base_url}/.well-known/jwks.json",
        "discovery_uri": f"{settings.base_url}/.well-known/openid-configuration",
        "auth_config_uri": f"{settings.base_url}/.well-known/auth-config",
        "active_kid": runtime.keystore.active_kid(),
        "active_fingerprint": runtime.keystore.fingerprint(),
        "all_kids": kids,
        "token_ttl": settings.token_ttl,
        "ticket_ttl": settings.ticket_ttl,
        "registration_mode": settings.allow_registration,
        "instances": [instances_repo.detail(runtime.db, inst)
                      for inst in instances_repo.list_instances(runtime.db)],
    })

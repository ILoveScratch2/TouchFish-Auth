"""管理员接口。

权限来自 users.role = 'admin'，用 CLI 授予：
    python -m app.cli promote <username>
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..deps import api_error, client_ip, current_user, user_agent
from ..runtime import get as get_runtime
from ..services import captcha as captcha_service
from ..services import instances as instances_repo
from ..services import site
from ..services import users as users_service
from ..services.binding import list_connections

router = APIRouter()


def _require_admin(request: Request):
    user = current_user(request)
    if user is None:
        return None, api_error(401, "not_authenticated", "请先登录")
    if user.get("role") != "admin":
        return None, api_error(403, "forbidden", "需要管理员权限")
    return user, None


class RoleBody(BaseModel):
    role: str = Field(pattern="^(user|admin)$")


class StatusBody(BaseModel):
    status: str = Field(pattern="^(active|suspended)$")


class InstanceBody(BaseModel):
    id: str = Field(min_length=1, max_length=32, pattern="^[a-z0-9_-]+$")
    base_url: str = Field(min_length=8, max_length=256)
    display_name: str = Field(min_length=1, max_length=64)
    audience: str | None = Field(default=None, max_length=128)


@router.get("/api/admin/overview")
def overview(request: Request):
    admin, error = _require_admin(request)
    if error:
        return error
    runtime = get_runtime()
    db = runtime.db

    users = users_service.list_users(db)
    sessions = db.query_one(
        "SELECT COUNT(*) AS n FROM sessions WHERE revoked_at IS NULL AND expires_at > ?",
        (time.time(),),
    )
    connections = db.query_one("SELECT COUNT(*) AS n FROM connections")
    bound_users = db.query_one("SELECT COUNT(DISTINCT user_id) AS n FROM connections")

    return JSONResponse({
        "me": {"id": admin["user_id"], "username": admin["username"], "role": admin["role"]},
        "stats": {
            "users": len(users),
            "admins": users_service.count_admins(db),
            "active_sessions": int(sessions["n"]) if sessions else 0,
            "connections": int(connections["n"]) if connections else 0,
            "bound_users": int(bound_users["n"]) if bound_users else 0,
        },
        "users": users,
        "instances": [instances_repo.detail(db, inst)
                      for inst in instances_repo.list_instances(db)],
        "keys": {
            "active_kid": runtime.keystore.active_kid(),
            "all_kids": [entry.kid for entry in runtime.keystore.public_entries()],
        },
        "registration_mode": runtime.settings.allow_registration,
    })


@router.post("/api/admin/users/{user_id}/role")
def set_role(user_id: str, body: RoleBody, request: Request):
    admin, error = _require_admin(request)
    if error:
        return error
    runtime = get_runtime()
    target = users_service.get(runtime.db, user_id)
    if target is None:
        return api_error(404, "user_not_found", "用户不存在")
    if target["role"] == "admin" and body.role == "user" and admin["user_id"] == user_id:
        return api_error(409, "cannot_demote_self", "不能取消自己的管理员权限")
    if not users_service.set_role(runtime.db, user_id, body.role):
        return api_error(400, "update_failed", "更新失败")
    runtime.db.audit("admin.role", admin["user_id"], client_ip(request),
                     user_agent(request), detail=f"{target['username']}:{body.role}")
    return JSONResponse({"ok": True})


@router.post("/api/admin/users/{user_id}/status")
def set_status(user_id: str, body: StatusBody, request: Request):
    admin, error = _require_admin(request)
    if error:
        return error
    runtime = get_runtime()
    target = users_service.get(runtime.db, user_id)
    if target is None:
        return api_error(404, "user_not_found", "用户不存在")
    if admin["user_id"] == user_id and body.status == "suspended":
        return api_error(409, "cannot_suspend_self", "不能停用自己")
    if not users_service.set_status(runtime.db, user_id, body.status):
        return api_error(400, "update_failed", "更新失败")
    runtime.db.audit("admin.status", admin["user_id"], client_ip(request),
                     user_agent(request), detail=f"{target['username']}:{body.status}")
    return JSONResponse({"ok": True})


@router.put("/api/admin/instances/{instance_id}")
def upsert_instance(instance_id: str, body: InstanceBody, request: Request):
    admin, error = _require_admin(request)
    if error:
        return error
    if body.id != instance_id:
        return api_error(400, "id_mismatch", "路径与请求体中的实例 id 不一致")
    runtime = get_runtime()
    try:
        instance = instances_repo.upsert(
            runtime.db, runtime.settings,
            instance_id=instance_id,
            base_url=body.base_url,
            display_name=body.display_name,
            audience=body.audience,
        )
    except ValueError as exc:
        return api_error(400, "invalid_instance", str(exc))
    runtime.db.audit("admin.instance", admin["user_id"], client_ip(request),
                     user_agent(request), detail=f"{instance.id}:{instance.base_url}")
    return JSONResponse({"instance": instances_repo.detail(runtime.db, instance)})


@router.post("/api/admin/keys/rotate")
def rotate_keys(request: Request):
    admin, error = _require_admin(request)
    if error:
        return error
    runtime = get_runtime()
    entry = runtime.keystore.rotate()
    runtime.db.audit("admin.key_rotate", admin["user_id"], client_ip(request),
                     user_agent(request), detail=entry.kid)
    return JSONResponse({
        "active_kid": entry.kid,
        "all_kids": [item.kid for item in runtime.keystore.public_entries()],
    })


@router.get("/api/admin/users/{user_id}/connections")
def user_connections(user_id: str, request: Request):
    admin, error = _require_admin(request)
    if error:
        return error
    runtime = get_runtime()
    return JSONResponse({"connections": list_connections(runtime.db, user_id)})


# ---------- 站点配置 ----------

class SettingsBody(BaseModel):
    values: dict


@router.get("/api/admin/settings")
def get_settings(request: Request):
    admin, error = _require_admin(request)
    if error:
        return error
    runtime = get_runtime()
    return JSONResponse(site.admin_view(runtime.db, runtime.settings))


@router.put("/api/admin/settings")
def put_settings(body: SettingsBody, request: Request):
    admin, error = _require_admin(request)
    if error:
        return error
    runtime = get_runtime()
    try:
        site.update(runtime.db, runtime.settings, body.values, admin["user_id"])
    except site.SettingsError as exc:
        return api_error(400, "invalid_setting", exc.message)
    runtime.db.audit(
        "admin.settings", admin["user_id"], client_ip(request), user_agent(request),
        # 只记键名，不记值 —— 值里可能有 SMTP 密码
        detail=",".join(sorted(body.values.keys())),
    )
    return JSONResponse(site.admin_view(runtime.db, runtime.settings))


# ---------- 审计日志 ----------

@router.get("/api/admin/audit")
def audit_log(request: Request, limit: int = 100, event: str = ""):
    admin, error = _require_admin(request)
    if error:
        return error
    runtime = get_runtime()
    limit = max(1, min(limit, 500))
    if event:
        rows = runtime.db.query(
            "SELECT * FROM audit_log WHERE event LIKE ? ORDER BY at DESC LIMIT ?",
            (f"{event}%", limit),
        )
    else:
        rows = runtime.db.query(
            "SELECT * FROM audit_log ORDER BY at DESC LIMIT ?", (limit,)
        )
    return JSONResponse({"entries": [
        {
            "id": row["id"],
            "at": row["at"],
            "event": row["event"],
            "user_id": row["user_id"],
            "ip": row["ip"],
            "user_agent": row["user_agent"],
            "detail": row["detail"],
        }
        for row in rows
    ]})


# ---------- 实例删除 / 强制下线 ----------

@router.delete("/api/admin/instances/{instance_id}")
def delete_instance(instance_id: str, request: Request):
    admin, error = _require_admin(request)
    if error:
        return error
    runtime = get_runtime()
    ok, message = instances_repo.delete(runtime.db, instance_id)
    if not ok:
        return api_error(409, "instance_delete_blocked", message)
    runtime.db.audit("admin.instance_delete", admin["user_id"], client_ip(request),
                     user_agent(request), detail=instance_id)
    return JSONResponse({"ok": True})


@router.post("/api/admin/users/{user_id}/logout-all")
def logout_all(user_id: str, request: Request):
    admin, error = _require_admin(request)
    if error:
        return error
    runtime = get_runtime()
    target = users_service.get(runtime.db, user_id)
    if target is None:
        return api_error(404, "user_not_found", "用户不存在")
    count = runtime.db.execute(
        "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
        (time.time(), user_id),
    )
    runtime.db.audit("admin.logout_all", admin["user_id"], client_ip(request),
                     user_agent(request), detail=target["username"])
    return JSONResponse({"ok": True, "revoked": count})


# ---------- 人机验证自检 ----------

@router.post("/api/admin/captcha/test")
def captcha_test(request: Request):
    """用当前配置向 siteverify 发一次探测，把 error-codes 原样返回
    """
    admin, error = _require_admin(request)
    if error:
        return error
    runtime = get_runtime()
    values = site.all_values(runtime.db, runtime.settings)

    if not (values["captcha_enabled"] or values["captcha_on_login"]):
        return api_error(409, "captcha_disabled", "当前没有启用人机验证")

    result = captcha_service.verify_detail(
        str(values["captcha_provider"]),
        str(values["captcha_secret"]),
        "probe-token",
        remote_ip=client_ip(request),
        verify_url=str(values.get("captcha_verify_url") or ""),
    )

    if not result.reachable:
        hint = "网络不通：检查服务器的出站网络或代理设置"
    elif "invalid-input-secret" in result.codes or "missing-input-secret" in result.codes:
        hint = "Secret 不正确：请从服务商控制台重新复制 Secret"
    elif "invalid-input-response" in result.codes or "timeout-or-duplicate" in result.codes:
        hint = "配置正确：Secret 有效（探测用的假 token 被拒绝属正常）"
    elif result.ok:
        hint = "配置可用"
    else:
        hint = result.message

    payload = result.as_dict()
    payload["hint"] = hint
    payload["provider"] = values["captcha_provider"]
    return JSONResponse(payload)

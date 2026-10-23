"""TouchFish Auth
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from .db import Db
from .deps import api_error, csrf_ok
from .routers import admin, auth, connections, tokens, wellknown
from .runtime import get as get_runtime
from .runtime import init as init_runtime
from .security.signer import KeyStore
from .services import binding as binding_service
from .services import instances as instances_repo
from .services import throttle as throttle_service
from .services import tfv5 as tfv5_service
from .settings import ConfigError, load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("touchfish-auth")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    db = Db(settings.db_path)
    keystore = KeyStore(settings.key_dir)

    init_runtime(settings, db, keystore)
    binding_service.attach_keystore(keystore)
    tfv5_service.init_client(settings.tfv5_allow_insecure_http)
    instances_repo.seed_default(db, settings)

    log.info("issuer=%s", settings.issuer)
    log.info("jwks=%s/.well-known/jwks.json", settings.base_url)
    log.info("active kid=%s", keystore.active_kid())
    log.info("registration mode=%s", settings.allow_registration)
    admins = db.query_one("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'")
    if admins and int(admins["n"]) == 0:
        log.warning("尚无管理员。授予方式：python -m app.cli promote <用户名>")
    if not settings.cookie_secure:
        log.warning("AUTH_COOKIE_SECURE=0：仅适用于本地 http 调试")
    if settings.dev_mail:
        log.warning("AUTH_DEV_MAIL=1：邮件不外发，写入 /api/dev/outbox。生产环境必须关闭")
    if not settings.frontend_dist.is_dir():
        log.warning("未找到前端产物 %s，仅提供 API", settings.frontend_dist)

    _prune_once(db)
    task = asyncio.create_task(_prune_loop(db))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _prune_once(db: Db) -> None:
    try:
        removed = db.prune()
        pruned = throttle_service.get().prune()
        if any(removed.values()) or pruned:
            log.info("清理过期数据 %s，回收登录限流桶 %s 个", removed, pruned)
    except Exception:  # noqa: BLE001 - 清理失败不该阻止服务启动
        log.exception("清理过期数据失败")


async def _prune_loop(db: Db) -> None:
    while True:
        await asyncio.sleep(6 * 3600)
        _prune_once(db)


app = FastAPI(title="TouchFish Auth", version="0.1.0", lifespan=lifespan,
              docs_url=None, redoc_url=None)


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.url.path.startswith("/api/") and not csrf_ok(request):
        return api_error(403, "csrf_failed", "请求校验失败，请刷新页面重试")
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.get("/api/health")
def health():
    return JSONResponse({"ok": True})


@app.post("/api/dev/throttle/reset")
def dev_throttle_reset():
    """清空登录失败计数。仅 AUTH_DEV_MAIL=1 时存在，供自动化测试使用。"""
    try:
        settings = get_runtime().settings
    except RuntimeError:
        return JSONResponse({"error": {"code": "not_started", "message": "服务尚未就绪"}},
                            status_code=503)
    if not settings.dev_mail:
        return JSONResponse({"error": {"code": "not_found", "message": "接口不存在"}},
                            status_code=404)
    throttle_service.get().reset_all()
    return JSONResponse({"ok": True})


@app.get("/api/dev/outbox")
def dev_outbox():
    """本地联调用的假收件箱。仅在 AUTH_DEV_MAIL=1 时存在，否则 404。"""
    try:
        settings = get_runtime().settings
    except RuntimeError:
        return JSONResponse({"error": {"code": "not_started", "message": "服务尚未就绪"}},
                            status_code=503)
    if not settings.dev_mail:
        return JSONResponse({"error": {"code": "not_found", "message": "接口不存在"}},
                            status_code=404)
    from .services.mailer import DEV_OUTBOX

    return JSONResponse({"mails": DEV_OUTBOX[-20:]})


app.include_router(wellknown.router)
app.include_router(auth.router)
app.include_router(connections.router)
app.include_router(tokens.router)
app.include_router(admin.router)


@app.get("/{full_path:path}")
def spa(full_path: str):
    """前端静态文件与 SPA 回退。

    在导入期就注册，避免"启动时再挂路由"导致路由表与预期不一致。
    """
    if full_path.startswith(("api/", ".well-known/")):
        return JSONResponse({"error": {"code": "not_found", "message": "接口不存在"}},
                            status_code=404)
    try:
        dist: Path = get_runtime().settings.frontend_dist
    except RuntimeError:
        return JSONResponse({"error": {"code": "not_started", "message": "服务尚未就绪"}},
                            status_code=503)

    if full_path:
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist)
        except ValueError:
            return JSONResponse({"error": {"code": "not_found", "message": "路径非法"}},
                                status_code=404)
        if candidate.is_file():
            return FileResponse(str(candidate))

    index = dist / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return JSONResponse({"error": {"code": "no_frontend", "message": "前端未构建"}},
                        status_code=503)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    try:
        load_settings()
    except ConfigError as exc:
        raise SystemExit(f"配置错误：{exc}") from exc
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)

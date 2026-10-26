"""发现端点"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..runtime import get as get_runtime
from ..services import instances as instances_repo
from ..services import oauth, site

router = APIRouter()


@router.get("/.well-known/jwks.json")
def jwks() -> JSONResponse:
    runtime = get_runtime()
    return JSONResponse(
        runtime.keystore.jwks(),
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/.well-known/openid-configuration")
def openid_configuration() -> JSONResponse:
    runtime = get_runtime()
    base = runtime.settings.base_url
    document = {
        "issuer": runtime.settings.issuer,
        "jwks_uri": f"{base}/.well-known/jwks.json",
        "id_token_signing_alg_values_supported": ["RS256"],
        "subject_types_supported": ["public"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "scopes_supported": ["openid", "profile", "email"],
        "claims_supported": [
            "iss", "sub", "aud", "exp", "iat", "nbf", "jti",
            "preferred_username", "email", "tfv5_uid",
        ],
        "authorization_endpoint": f"{base}/authorize",
        "ticket_endpoint": f"{base}/api/auth/ticket",
        "userinfo_endpoint": f"{base}/api/userinfo",
    }
    return JSONResponse(document, headers={"Cache-Control": "public, max-age=300"})


@router.get("/.well-known/auth-config")
def auth_config() -> JSONResponse:
    """客户端登录页据此渲染登录方式，避免客户端硬编码 provider。"""
    runtime = get_runtime()
    base = runtime.settings.base_url
    site_values = site.all_values(runtime.db, runtime.settings)
    methods: list[dict] = [
        {
            "id": "password",
            "kind": "password",
            "display_name": f"{site_values['site_name']} 账号",
            "enabled": True,
        }
    ]
    if instances_repo.get_instance(runtime.db, None) is not None:
        methods.append({
            "id": "tfv5",
            "kind": "tfv5",
            "display_name": "TouchFish 账号",
            "enabled": True,
            "hint": "使用 TouchFish 服务器账号密码登录",
        })
    methods.extend(oauth.methods(runtime.db, runtime.settings, base))

    return JSONResponse(
        {
            "issuer": runtime.settings.issuer,
            "site_name": site_values["site_name"],
            "authorization_endpoint": f"{base}/authorize",
            "ticket_endpoint": f"{base}/api/auth/ticket",
            "methods": methods,
        },
        headers={"Cache-Control": "public, max-age=60"},
    )

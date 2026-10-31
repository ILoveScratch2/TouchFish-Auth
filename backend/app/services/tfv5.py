"""TFV5 客户端 
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..security.envelope import (
    EnvelopeError,
    build_envelope,
    load_public_key,
    open_envelope,
)

PUB_KEY_TTL = 3600.0
STATUS_TIMEOUT = 5.0
CALL_TIMEOUT = 10.0
# 本地节流：每分钟最多 120 次登录/绑定
LOCAL_LIMIT_PER_MINUTE = 120


class Tfv5Error(RuntimeError):
    def __init__(self, code: str, message: str = "", status: int | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.status = status


@dataclass
class Instance:
    id: str
    base_url: str
    display_name: str
    issuer: str
    audience: str | None
    allow_insecure_http: bool


class _Bucket:
    """按 (instance, path) 的滑动窗口。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[tuple[str, str], list[float]] = {}

    def allow(self, instance_id: str, path: str, limit: int = LOCAL_LIMIT_PER_MINUTE) -> bool:
        key = (instance_id, path)
        now = time.time()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if t > now - 60]
            if len(hits) >= limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


_bucket = _Bucket()


class Tfv5Client:
    def __init__(self, allow_insecure_http: bool) -> None:
        self._allow_insecure_http = allow_insecure_http
        self._pub_cache: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()
        # trust_env=False：不读 HTTP(S)_PROXY
        self._client = httpx.Client(timeout=CALL_TIMEOUT, follow_redirects=False,
                                    trust_env=False)


    def _check_url(self, base_url: str, allow_insecure: bool | None = None) -> str:
        allow_insecure = self._allow_insecure_http if allow_insecure is None else allow_insecure
        if base_url.startswith("https://"):
            return base_url.rstrip("/")
        if base_url.startswith("http://"):
            if not allow_insecure:
                raise Tfv5Error(
                    "tfv5_insecure_disabled",
                    f"{base_url} 是明文 HTTP，但未允许。本地联调请设 AUTH_TFV5_ALLOW_INSECURE_HTTP=1",
                )
            return base_url.rstrip("/")
        raise Tfv5Error("tfv5_invalid_url", f"无效的 TFV5 地址：{base_url}")

    def public_key(self, instance: Instance) -> str:
        base = self._check_url(instance.base_url, instance.allow_insecure_http)
        with self._lock:
            cached = self._pub_cache.get(base)
        if cached and time.time() - cached[1] < PUB_KEY_TTL:
            return cached[0]
        try:
            resp = self._client.get(f"{base}/get_rsa_pub")
        except httpx.HTTPError as exc:
            raise Tfv5Error("tfv5_unreachable", f"无法连接 TFV5：{exc}") from exc
        if resp.status_code != 200 or b"BEGIN PUBLIC KEY" not in resp.content:
            raise Tfv5Error("tfv5_bad_pubkey", f"取公钥失败（HTTP {resp.status_code}）")
        pem = resp.text
        with self._lock:
            self._pub_cache[base] = (pem, time.time())
        return pem

    def _envelope_call(self, instance: Instance, path: str,
                       payload: dict[str, Any], throttle: bool = True) -> dict[str, Any]:
        if throttle and not _bucket.allow(instance.id, path):
            raise Tfv5Error("tfv5_throttled", "本地节流：请求过于频繁，请稍后重试", 429)
        base = self._check_url(instance.base_url, instance.allow_insecure_http)
        pub = load_public_key(self.public_key(instance))
        body, aes_key = build_envelope(pub, payload)
        try:
            resp = self._client.post(f"{base}{path}", json=body)
        except httpx.HTTPError as exc:
            raise Tfv5Error("tfv5_unreachable", f"无法连接 TFV5：{exc}") from exc

        # 注意：401/403 的 body 同样是信封，必须先解密
        try:
            return open_envelope(aes_key, resp.content)
        except EnvelopeError as exc:
            if resp.status_code == 429:
                raise Tfv5Error("tfv5_rate_limited", "TFV5 侧触发限流", 429) from exc
            if resp.status_code in (403, 404):
                raise Tfv5Error("tfv5_rejected", f"TFV5 拒绝了该请求（HTTP {resp.status_code}）",
                                resp.status_code) from exc
            raise Tfv5Error("tfv5_protocol_error",
                            f"TFV5 响应无法解密（HTTP {resp.status_code}）", resp.status_code) from exc

    def _plain_get(self, instance: Instance, path: str, params: dict[str, str] | None = None) -> Any:
        base = self._check_url(instance.base_url, instance.allow_insecure_http)
        try:
            resp = self._client.get(f"{base}{path}", params=params, timeout=STATUS_TIMEOUT)
        except httpx.HTTPError as exc:
            raise Tfv5Error("tfv5_unreachable", f"无法连接 TFV5：{exc}") from exc
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    # ---------- 业务 ----------

    def status(self, instance: Instance, iss: str, sub: str) -> dict[str, Any] | None:
        """探测专用端点是否可用。

        返回 dict 表示端点可用；None 表示该 TFV5 没有 /auth/platform/*
        （旧版）或被 IP/令牌拒绝 —— 两种情况都该降级走旧链路。
        """
        try:
            return self._plain_get(instance, "/auth/platform/status", {"iss": iss, "sub": sub})
        except Tfv5Error:
            return None

    def username_lookup(self, instance: Instance, username: str) -> dict[str, Any] | None:
        return self._plain_get(instance, f"/auth/username/{username}")

    def platform_bind(self, instance: Instance, *, iss: str, sub: str,
                      identifier: str, password: str) -> dict[str, Any]:
        return self._envelope_call(instance, "/auth/platform/bind", {
            "identifier": identifier,
            "password": password,
            "iss": iss,
            "sub": sub,
            "detail_error": True,
        })

    def platform_unbind(self, instance: Instance, *, iss: str, sub: str) -> dict[str, Any]:
        return self._envelope_call(instance, "/auth/platform/unbind", {
            "iss": iss,
            "sub": sub,
            "detail_error": True,
        })

    def resolve_uid(self, instance: Instance, identifier: str) -> int:
        text = identifier.strip()
        if text.isdigit():
            return int(text)
        info = self.username_lookup(instance, text)
        if not info or "uid" not in info:
            raise Tfv5Error("tfv5_user_not_found", "该 TouchFish 账号不存在")
        try:
            return int(info["uid"])
        except (TypeError, ValueError) as exc:
            raise Tfv5Error("tfv5_user_not_found", "该 TouchFish 账号不存在") from exc

    def login(self, instance: Instance, *, identifier: str, password: str) -> dict[str, Any]:
        """旧链路：用 uid+密码换 TFV5 会话（会建会话，仅降级时使用）。"""
        uid = self.resolve_uid(instance, identifier)
        result = self._envelope_call(instance, "/auth/login", {
            "uid": uid,
            "password": password,
            "jwt": True,
            "detail_error": True,
            "device_id": f"touchfish-auth-{instance.id}",
            "device_name": "TouchFish Auth",
            "platform": 0,
        })
        if "token" not in result:
            code = result.get("error", "tfv5_login_failed")
            if code in ("AUTH_FAILED", "AUTH_INVALID_PASSWORD", "auth_failed"):
                code = "auth_failed"
            elif code in ("RESOURCE_USER_BANNED", "user_banned"):
                code = "user_banned"
            raise Tfv5Error(code, "TouchFish 账号或密码不正确")
        result["uid"] = uid
        return result

    def external_bind(self, instance: Instance, *, token: str, external_token: str) -> dict[str, Any]:
        result = self._envelope_call(instance, "/auth/external/bind", {
            "token": token,
            "external_token": external_token,
            "detail_error": True,
        })
        if result.get("success") is not True:
            code = result.get("error", "external_bind_failed")
            raise Tfv5Error(code, "该 TouchFish 账号已关联其他平台账户")
        return result

    def info(self, instance: Instance) -> dict[str, Any] | None:
        data = self._plain_get(instance, "/info")
        return data if isinstance(data, dict) else None


client: Tfv5Client | None = None


def init_client(allow_insecure_http: bool) -> Tfv5Client:
    global client
    client = Tfv5Client(allow_insecure_http)
    return client


def get_client() -> Tfv5Client:
    if client is None:  # pragma: no cover - 由 main.py 保证已初始化
        raise Tfv5Error("tfv5_client_uninitialized", "TFV5 客户端未初始化")
    return client

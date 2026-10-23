"""人机验证（Cloudflare Turnstile / hCaptcha）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

OFFICIAL_URLS = {
    "turnstile": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    "hcaptcha": "https://hcaptcha.com/siteverify",
}

CODE_HINTS = {
    "missing-input-secret": "未配置 Secret",
    "invalid-input-secret": "Secret 不正确",
    "missing-input-response": "未收到验证 token",
    "invalid-input-response": "token 无效",
    "timeout-or-duplicate": "token 已使用或已超时，请重新验证",
    "invalid-or-already-seen-response": "token 已使用，请重新验证",
    "sitekey-secret-mismatch": "Site Key 与 Secret 不匹配",
    "bad-request": "请求格式不正确",
    "internal-error": "验证服务暂时不可用",
}


@dataclass
class CaptchaResult:
    ok: bool
    codes: list[str] = field(default_factory=list)
    message: str = ""
    reachable: bool = True
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "codes": self.codes,
            "message": self.message,
            "reachable": self.reachable,
            "detail": self.detail,
        }


def _interpret(payload: dict) -> CaptchaResult:
    codes = [str(item) for item in (payload.get("error-codes") or [])]
    if payload.get("success") is True:
        return CaptchaResult(ok=True, codes=[], message="验证通过")
    if not codes:
        return CaptchaResult(ok=False, codes=[], message="验证未通过")
    return CaptchaResult(
        ok=False,
        codes=codes,
        message="；".join(CODE_HINTS.get(code, code) for code in codes),
    )


def verify_detail(
    provider: str,
    secret: str,
    token: str,
    *,
    remote_ip: str | None = None,
    verify_url: str = "",
    timeout: float = 8.0,
) -> CaptchaResult:
    if not secret:
        return CaptchaResult(ok=False, message="未配置 Secret")
    url = verify_url.strip() or OFFICIAL_URLS.get(provider, "")
    if not url:
        return CaptchaResult(ok=False, message=f"未知的验证码服务商：{provider}")

    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        # 出站到公网，按环境代理走（与 TFV5 的本地直连相反）
        with httpx.Client(trust_env=True, timeout=timeout) as client:
            response = client.post(url, data=payload)
    except Exception as exc:  # noqa: BLE001 - 网络异常要能说清是网络问题
        return CaptchaResult(
            ok=False,
            reachable=False,
            message="无法连接验证服务（检查出站网络或代理）",
            detail=f"{type(exc).__name__}: {exc}"[:200],
        )

    try:
        data = response.json()
    except ValueError:
        return CaptchaResult(
            ok=False,
            reachable=False,
            message=f"验证服务返回了非 JSON 响应（HTTP {response.status_code}）",
            detail=response.text[:200],
        )

    if not isinstance(data, dict):
        return CaptchaResult(ok=False, message="验证服务响应格式异常")

    result = _interpret(data)
    if response.status_code >= 400 and result.ok:
        return CaptchaResult(ok=False, message=f"验证服务状态异常（HTTP {response.status_code}）")
    return result


def verify(
    provider: str,
    secret: str,
    token: str,
    *,
    remote_ip: str | None = None,
    verify_url: str = "",
    timeout: float = 8.0,
) -> bool:
    return verify_detail(
        provider, secret, token,
        remote_ip=remote_ip, verify_url=verify_url, timeout=timeout,
    ).ok

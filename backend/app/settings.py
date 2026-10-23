"""运行时配置。

按需求「生产地址部署时确定」，这里不提供任何可用作生产的默认 issuer：
缺 AUTH_BASE_URL 直接抛错并给出明确提示。
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """极简 .env 解析：KEY=VALUE，# 注释，不覆盖已存在的环境变量。"""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _str(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _split(name: str) -> list[str]:
    raw = os.environ.get(name) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    base_url: str
    issuer: str
    db_path: Path
    key_dir: Path
    master_key: bytes
    allow_registration: str
    default_instance_url: str
    default_instance_id: str
    tfv5_allow_insecure_http: bool
    session_ttl: int
    token_ttl: int
    ticket_ttl: int
    cookie_secure: bool
    allowed_origins: list[str]
    frontend_dist: Path
    dev_mail: bool
    site_name: str
    trust_proxy: bool

    @property
    def cookie_domain(self) -> str | None:
        return None


def load_settings(env_file: Path | None = None) -> Settings:
    _load_dotenv(env_file or (_BACKEND_DIR / ".env"))

    base_url = _str("AUTH_BASE_URL").rstrip("/")
    if not base_url:
        raise ConfigError(
            "AUTH_BASE_URL 未设置。这是必填项：它决定 issuer 与 JWKS 地址，"
            "且必须与 TFV5 的 jwt_external_issuers[].iss 完全一致。"
            "\n示例：cp .env.example .env 后填写 AUTH_BASE_URL=http://127.0.0.1:8000"
        )

    issuer = (_str("AUTH_ISSUER") or base_url).rstrip("/")
    if issuer != base_url:
        # 允许分离（平台在反代后面），但必须显式配置，避免静默不一致
        pass

    master_raw = _str("AUTH_MASTER_KEY")
    if not master_raw:
        raise ConfigError(
            "AUTH_MASTER_KEY 未设置。用于加密缓存的 TFV5 refresh token。"
            "\n生成：python -c \"import os,base64;print(base64.b64encode(os.urandom(32)).decode())\""
        )
    try:
        master_key = base64.b64decode(master_raw, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ConfigError("AUTH_MASTER_KEY 必须是 base64") from exc
    if len(master_key) != 32:
        raise ConfigError(f"AUTH_MASTER_KEY 解码后必须是 32 字节，当前 {len(master_key)}")

    mode = _str("AUTH_ALLOW_REGISTRATION", "follow_tfv5")
    if mode not in ("follow_tfv5", "force_on", "force_off"):
        raise ConfigError("AUTH_ALLOW_REGISTRATION 只能是 follow_tfv5 / force_on / force_off")

    return Settings(
        base_url=base_url,
        issuer=issuer,
        db_path=(_BACKEND_DIR / _str("AUTH_DB_PATH", "./data/auth.db")).resolve(),
        key_dir=(_BACKEND_DIR / _str("AUTH_KEY_DIR", "./keys")).resolve(),
        master_key=master_key,
        allow_registration=mode,
        default_instance_url=_str("AUTH_DEFAULT_INSTANCE_URL").rstrip("/"),
        default_instance_id=_str("AUTH_DEFAULT_INSTANCE_ID", "main"),
        tfv5_allow_insecure_http=_bool("AUTH_TFV5_ALLOW_INSECURE_HTTP", False),
        session_ttl=_int("AUTH_SESSION_TTL", 604800),
        token_ttl=_int("AUTH_TOKEN_TTL", 300),
        ticket_ttl=_int("AUTH_TICKET_TTL", 60),
        cookie_secure=_bool("AUTH_COOKIE_SECURE", True),
        allowed_origins=_split("AUTH_ALLOWED_ORIGINS"),
        frontend_dist=(_BACKEND_DIR.parent / "frontend" / "dist").resolve(),
        dev_mail=_bool("AUTH_DEV_MAIL", False),
        site_name=_str("AUTH_SITE_NAME", "TouchFish Auth"),
        trust_proxy=_bool("AUTH_TRUST_PROXY", False),
    )

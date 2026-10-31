"""
RS256 密钥环、JWKS 与 token 签发
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ALGORITHM = "RS256"
KEY_BITS = 3072
RETENTION_SECONDS = 7 * 24 * 3600  # 旧公钥保留 7 天


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _int_to_b64(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return b64url(value.to_bytes(length, "big"))


@dataclass
class KeyEntry:
    kid: str
    private_pem: bytes
    public_numbers: tuple[int, int]  # (n, e)
    created_at: float
    retired_at: float | None

    @property
    def active(self) -> bool:
        return self.retired_at is None


class KeyStore:
    """目录式密钥环：index.json + <kid>.pem（0600）。"""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._index_path = self._dir / "index.json"
        self._keys: list[KeyEntry] = []
        self._load()

    # 持久化 

    def _load(self) -> None:
        with self._lock:
            raw = None
            if self._index_path.is_file():
                try:
                    raw = json.loads(self._index_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    raw = None
            entries: list[KeyEntry] = []
            root = self._dir.resolve()
            for item in (raw or {}).get("keys", []):
                try:
                    # index.json 里的 file 不可信
                    name = item["file"]
                    if not isinstance(name, str) or not name:
                        continue
                    pem_path = (root / name).resolve()
                    if pem_path.parent != root:
                        continue
                    pem = pem_path.read_bytes()
                    key = serialization.load_pem_private_key(pem, password=None)
                except Exception:  # noqa: BLE001
                    continue
                if not isinstance(key, rsa.RSAPrivateKey):
                    continue
                nums = key.public_key().public_numbers()
                # kid 推导
                entries.append(KeyEntry(
                    kid=_thumbprint(nums.n, nums.e),
                    private_pem=pem,
                    public_numbers=(nums.n, nums.e),
                    created_at=float(item.get("created_at", time.time())),
                    retired_at=item.get("retired_at"),
                ))
            self._keys = entries
            if not self._keys:
                self._create()

    def _save_index(self) -> None:
        payload = {
            "keys": [
                {
                    "kid": entry.kid,
                    "alg": ALGORITHM,
                    "file": f"{entry.kid}.pem",
                    "created_at": entry.created_at,
                    "retired_at": entry.retired_at,
                }
                for entry in self._keys
            ]
        }
        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self._index_path)

    def _create(self) -> KeyEntry:
        key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_BITS)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        nums = key.public_key().public_numbers()
        kid = _thumbprint(nums.n, nums.e)
        pem_path = self._dir / f"{kid}.pem"
        pem_path.write_bytes(pem)
        try:
            os.chmod(pem_path, 0o600)
        except OSError:
            pass  # Windows 上不管
        entry = KeyEntry(kid=kid, private_pem=pem, public_numbers=(nums.n, nums.e),
                         created_at=time.time(), retired_at=None)
        self._keys.append(entry)
        self._save_index()
        return entry


    def _active(self) -> KeyEntry:
        with self._lock:
            for entry in self._keys:
                if entry.active:
                    return entry
            return self._create()

    def active_kid(self) -> str:
        return self._active().kid

    def public_entries(self) -> list[KeyEntry]:
        """
        发布用
        活跃的 + 仍在保留期内的

        神秘设计有些 CCF dzd 会偷懒取 keys[0]。虽然按 kid 选择才是正确做法
        """
        now = time.time()
        with self._lock:
            published = [
                entry for entry in self._keys
                if entry.active or (entry.retired_at and now - entry.retired_at < RETENTION_SECONDS)
            ]
        published.sort(key=lambda entry: (not entry.active, entry.created_at))
        return published

    def jwks(self) -> dict[str, Any]:
        keys = []
        for entry in self.public_entries():
            n, e = entry.public_numbers
            keys.append({
                "kty": "RSA",
                "use": "sig",
                "alg": ALGORITHM,
                "kid": entry.kid,
                "n": _int_to_b64(n),
                "e": _int_to_b64(e),
            })
        return {"keys": keys}

    def fingerprint(self, kid: str | None = None) -> str:
        """给开发者页展示的短指纹（kid 本身已是 thumbprint"""
        target = kid or self.active_kid()
        return " ".join(target[i:i + 4] for i in range(0, len(target), 4)).upper()

    def rotate(self) -> KeyEntry:
        with self._lock:
            for entry in self._keys:
                if entry.active:
                    entry.retired_at = time.time()
            entry = self._create()
            self._save_index()
            return entry


    def sign(self, claims: dict[str, Any], kid: str | None = None) -> str:
        entry = self._active()
        if kid and kid != entry.kid:
            for candidate in self._keys:
                if candidate.kid == kid:
                    entry = candidate
                    break
        payload = dict(claims)
        payload.setdefault("jti", uuid.uuid4().hex)
        return jwt.encode(
            payload,
            entry.private_pem,
            algorithm=ALGORITHM,
            headers={"kid": entry.kid, "typ": "JWT"},
        )


def _thumbprint(n: int, e: int) -> str:
    """RFC 7638：对按字典序排列的必需成员做 SHA-256"""
    canonical = json.dumps(
        {"e": _int_to_b64(e), "kty": "RSA", "n": _int_to_b64(n)},
        separators=(",", ":"),
        sort_keys=True,
    )
    return b64url(hashlib.sha256(canonical.encode("utf-8")).digest())

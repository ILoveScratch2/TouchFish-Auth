"""
平台账户的密码哈希

与 TFV5 的 Argon2id 参数无关
TFV5 的密码不落库
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# 注意到这比 TFV5 更强
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,   # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:  # noqa: BLE001
        return False


def needs_rehash(password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:  # noqa: BLE001
        return False

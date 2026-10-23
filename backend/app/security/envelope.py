"""TFV5 的 RSA+AES 信封，以及平台自用的 AES-GCM 密封。

信封格式与 TFV5_server/crypto.py 逐字节对齐：
  请求 {"key": b64(RSA-OAEP(aes_key)), "iv": b64(iv), "content": b64(ct)}
  RSA   OAEP(mgf=MGF1(SHA256), algorithm=SHA256, label=None)
  对称  AES-256-CBC + PKCS7(128)，key 32B，iv 16B
  响应  {"iv": b64, "content": b64}，用同一个 aes_key 解密

注意：TFV5 的失败响应（含 HTTP 401）同样是加密信封，调用方必须
先解密再判错，不能因为状态码非 200 就放弃。
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives import hashes, padding as sym_padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EnvelopeError(RuntimeError):
    pass


def load_public_key(pem: str | bytes) -> RSAPublicKey:
    if isinstance(pem, str):
        pem = pem.encode("utf-8")
    try:
        key = serialization.load_pem_public_key(pem)
    except Exception as exc:  # noqa: BLE001
        raise EnvelopeError("TFV5 公钥不是合法的 PEM") from exc
    if not isinstance(key, RSAPublicKey):
        raise EnvelopeError("TFV5 公钥不是 RSA")
    return key


def aes_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def aes_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def build_envelope(public_key: RSAPublicKey, payload: dict[str, Any]) -> tuple[dict[str, str], bytes]:
    """返回 (请求体, aes_key)。aes_key 留给调用方解响应。"""
    aes_key = os.urandom(32)
    iv = os.urandom(16)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ciphertext = aes_encrypt(body, aes_key, iv)
    wrapped = public_key.encrypt(
        aes_key,
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return (
        {
            "key": base64.b64encode(wrapped).decode("ascii"),
            "iv": base64.b64encode(iv).decode("ascii"),
            "content": base64.b64encode(ciphertext).decode("ascii"),
        },
        aes_key,
    )


def open_envelope(aes_key: bytes, response: Any) -> dict[str, Any]:
    """解密 TFV5 响应。response 是已解析的 JSON（dict）或原始 bytes/str。"""
    if isinstance(response, (bytes, bytearray)):
        try:
            response = json.loads(response.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise EnvelopeError("响应不是 JSON（可能是纯文本错误体）") from exc
    elif isinstance(response, str):
        try:
            response = json.loads(response)
        except Exception as exc:  # noqa: BLE001
            raise EnvelopeError("响应不是 JSON（可能是纯文本错误体）") from exc

    if not isinstance(response, dict) or "content" not in response or "iv" not in response:
        raise EnvelopeError("响应缺少 iv/content，可能被限流或路径错误")

    try:
        iv = base64.b64decode(response["iv"])
        ciphertext = base64.b64decode(response["content"])
        plaintext = aes_decrypt(ciphertext, aes_key, iv)
    except Exception as exc:  # noqa: BLE001
        raise EnvelopeError("响应解密失败") from exc

    text = plaintext.decode("utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # 老接口会返回 "<ts>True" / "<ts>False" 这种裸文本
        return {"raw": text}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


# ---------- 平台自用：加密缓存的 TFV5 refresh token ----------

def seal(master_key: bytes, plaintext: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(master_key).encrypt(nonce, plaintext.encode("utf-8"), b"tfv5-refresh")


def unseal(master_key: bytes, blob: bytes) -> str:
    if len(blob) < 13:
        raise EnvelopeError("密文长度异常")
    nonce, ciphertext = blob[:12], blob[12:]
    return AESGCM(master_key).decrypt(nonce, ciphertext, b"tfv5-refresh").decode("utf-8")

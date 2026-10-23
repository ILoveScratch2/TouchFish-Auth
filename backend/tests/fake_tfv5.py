"""假 TFV5，用于本地联调与测试。

它直接复用 TFV5_server 自己的 crypto.py 做信封加解密，
所以能真正验证"平台的信封实现"与"TFV5 的实现"互通，
而不是自己跟自己玩。

启动：python tests/fake_tfv5.py [端口]
接口：
  GET  /get_rsa_pub
  GET  /info
  GET  /auth/username/<name>
  GET  /auth/platform/status
  POST /auth/platform/bind      （不建会话）
  POST /auth/platform/unbind
  POST /auth/login              （建会话，用于验证降级路径）
  POST /auth/external/bind
  GET  /_debug/state             （测试用：看会话/绑定/调用记录）
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

TFV5_DIR = Path("D:/TouchFish-V5/TFV5_server")
sys.path.insert(0, str(TFV5_DIR))

from flask import Flask, jsonify, request  # noqa: E402

import crypto  # noqa: E402  ← TFV5 自己的实现

app = Flask(__name__)

HERE = Path(__file__).resolve().parent
KEY_DIR = HERE / "_keys"
KEY_DIR.mkdir(exist_ok=True)
PRI_PATH = KEY_DIR / "pri.pem"
PUB_PATH = KEY_DIR / "pub.pem"

if not PRI_PATH.is_file():
    # TFV5 的 generate_rsa_keys() 实际返回
    # (private_key, public_key, private_pem, public_pem, hash)
    # —— docstring 里写反了，这里按实际顺序取。
    result = crypto.generate_rsa_keys()
    private_pem, public_pem = result[2], result[3]
    PRI_PATH.write_bytes(private_pem if isinstance(private_pem, bytes) else private_pem.encode())
    PUB_PATH.write_bytes(public_pem if isinstance(public_pem, bytes) else public_pem.encode())

PRI = crypto.load_pri(str(PRI_PATH))

# 假数据
USERS = {
    1001: {"username": "alice", "password": "alice-password", "stat": "user"},
    1002: {"username": "bob", "password": "bob-password", "stat": "banned"},
    # 用于"换绑到他人已占用账号"的用例
    1003: {"username": "carol", "password": "carol-password", "stat": "user"},
}
ISS = os.environ.get("FAKE_TFV5_ISS", "http://127.0.0.1:8000")
ALLOW_REGISTER = os.environ.get("FAKE_TFV5_ALLOW_REGISTER", "1") == "1"
PLATFORM_ENDPOINTS = os.environ.get("FAKE_TFV5_PLATFORM", "1") == "1"

STATE = {
    "sessions": [],        # /auth/login 建的会话
    "identities": [],      # (iss, sub, uid)
    "platform_calls": [],  # 专用端点调用记录
    "login_calls": 0,
}


def _sealed(data: dict, status: int = 200):
    iv, ct = crypto.aes_encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"),
                                _current_key["k"])
    return jsonify({
        "iv": base64.b64encode(iv).decode(),
        "content": base64.b64encode(ct).decode(),
    }), status


_current_key: dict = {}


def _unwrap():
    aes_key, _iv, content = crypto.deal_req_data(request.get_json(), PRI)
    _current_key["k"] = aes_key
    return content


@app.get("/get_rsa_pub")
def get_rsa_pub():
    return PUB_PATH.read_text(), 200, {"Content-Type": "application/x-pem-file"}


@app.get("/info")
def info():
    return jsonify({
        "server_name": "Fake TouchFish",
        "port_api": 7001,
        "allow_register": ALLOW_REGISTER,
        "external_auth_url": ISS,
        "jwt_signing_algorithm": "RS256",
        "legacy_auth_enabled": True,
    })


@app.get("/auth/username/<name>")
def by_username(name: str):
    for uid, row in USERS.items():
        if row["username"].lower() == name.lower():
            return jsonify({"uid": uid, "username": row["username"], "stat": row["stat"]})
    return jsonify({})


@app.get("/_debug/state")
def debug_state():
    return jsonify(STATE)


@app.post("/_debug/reset")
def debug_reset():
    """清空身份映射与会话记录。测试可重复运行依赖这个入口。"""
    STATE["identities"].clear()
    STATE["sessions"].clear()
    STATE["platform_calls"].clear()
    STATE["login_calls"] = 0
    return jsonify({"ok": True})


@app.get("/auth/platform/status")
def platform_status():
    if not PLATFORM_ENDPOINTS:
        return "Not Found", 404
    iss = request.args.get("iss", "")
    sub = request.args.get("sub", "")
    for item in STATE["identities"]:
        if item["iss"] == iss and item["sub"] == sub:
            return jsonify({"linked": True, "uid": item["uid"],
                            "username": USERS.get(item["uid"], {}).get("username", "")})
    return jsonify({"linked": False})


@app.post("/auth/platform/bind")
def platform_bind():
    if not PLATFORM_ENDPOINTS:
        return "Not Found", 404
    body = _unwrap()
    STATE["platform_calls"].append({"at": time.time(), "path": "/auth/platform/bind"})
    iss = body.get("iss")
    sub = body.get("sub")
    identifier = str(body.get("identifier", ""))
    password = body.get("password", "")

    if iss != ISS:
        return _sealed({"error": "external_token_invalid"}, 400)

    uid = int(identifier) if identifier.isdigit() else None
    if uid is None:
        for key, row in USERS.items():
            if row["username"].lower() == identifier.lower():
                uid = key
                break
    if uid is None or USERS.get(uid, {}).get("password") != password:
        return _sealed({"error": "auth_failed"}, 401)
    row = USERS[uid]
    if row["stat"] == "banned":
        return _sealed({"error": "user_banned"}, 403)

    for item in STATE["identities"]:
        if item["iss"] == iss and item["sub"] == sub:
            if item["uid"] == uid:
                return _sealed({"success": True, "uid": uid,
                                "username": row["username"], "created": False})
            return _sealed({"error": "external_already_linked"}, 409)
        if item["iss"] == iss and item["uid"] == uid:
            return _sealed({"error": "external_already_linked"}, 409)

    STATE["identities"].append({"iss": iss, "sub": sub, "uid": uid})
    # 注意：这里刻意不建会话，用于验证平台链路不会污染用户设备列表
    return _sealed({"success": True, "uid": uid, "username": row["username"], "created": True})


@app.post("/auth/platform/unbind")
def platform_unbind():
    if not PLATFORM_ENDPOINTS:
        return "Not Found", 404
    body = _unwrap()
    iss, sub = body.get("iss"), body.get("sub")
    before = len(STATE["identities"])
    STATE["identities"][:] = [i for i in STATE["identities"]
                              if not (i["iss"] == iss and i["sub"] == sub)]
    return _sealed({"success": True, "removed": before - len(STATE["identities"])})


@app.post("/auth/login")
def login():
    body = _unwrap()
    STATE["login_calls"] += 1
    uid = int(body.get("uid") or 0)
    password = body.get("password", "")
    row = USERS.get(uid)
    if row is None or row["password"] != password:
        return _sealed({"error": "auth_failed"}, 401)
    if row["stat"] == "banned":
        return _sealed({"error": "user_banned"}, 403)
    sid = os.urandom(8).hex()
    STATE["sessions"].append({"sid": sid, "uid": uid, "device": body.get("device_name")})
    return _sealed({
        "token": f"fake-token-{sid}",
        "refresh_token": f"fake-refresh-{sid}",
        "expires_in": 3600,
        "refresh_expires_in": 604800,
    })


@app.post("/auth/refresh")
def refresh():
    body = _unwrap()
    token = str(body.get("refresh_token", ""))
    if not token.startswith("fake-refresh-"):
        return _sealed({"error": "token_expired"}, 401)
    return _sealed({"token": f"fake-token-rotated-{token[-8:]}",
                    "refresh_token": token + "-rot", "expires_in": 3600})


@app.post("/auth/external/bind")
def external_bind():
    body = _unwrap()
    iss = body.get("iss")
    sub = body.get("sub")
    STATE["identities"].append({"iss": iss, "sub": sub, "uid": -1, "legacy": True})
    return _sealed({"success": True})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7001
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

"""端到端冒烟：真 HTTP 打自己的 API，TFV5 侧用 tests/fake_tfv5.py。

前置：fake_tfv5 跑在 7001，本服务跑在 8000。
运行：python tests/smoke.py
"""
from __future__ import annotations

import base64
import json
import sys

from _fixtures import relaxed_site_settings
import time
from pathlib import Path

import httpx
import jwt

BASE = "http://127.0.0.1:8000"
FAKE = "http://127.0.0.1:7001"

ok_count = 0
fail_count = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global ok_count, fail_count
    if condition:
        ok_count += 1
        print(f"  PASS  {name}")
    else:
        fail_count += 1
        print(f"  FAIL  {name}  {detail}")


def main() -> int:
    # 站点若开着验证码/邮箱验证，本测试注册不出账号；夹具会在结束后原样还原配置
    with relaxed_site_settings():
        return _run()


def _run() -> int:
    client = httpx.Client(base_url=BASE, trust_env=False, timeout=20,
                          follow_redirects=False)
    fake = httpx.Client(base_url=FAKE, trust_env=False, timeout=10)

    print("\n[1] 发现端点")
    fake.post("/_debug/reset")  # 让本次运行从干净状态开始
    # 同时清掉本库里指向假 TFV5 账号的历史绑定：同一 (实例, tfv5_uid) 只能绑一个平台账户，
    # 上一次运行如果被中断，留下的绑定会让本次绑定返回 409。
    import sqlite3

    db_path = (Path(__file__).resolve().parent.parent / "data" / "auth.db")
    if db_path.is_file():
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM connections WHERE instance_id = 'main' AND tfv5_uid IN (1001, 1002)")
        conn.commit()
        conn.close()

    r = client.get("/.well-known/jwks.json")
    jwks = r.json()
    check("jwks 有公钥", r.status_code == 200 and len(jwks["keys"]) >= 1, str(r.status_code))
    check("算法 RS256", jwks["keys"][0]["alg"] == "RS256")
    check("kid 非空", bool(jwks["keys"][0]["kid"]))

    r = client.get("/.well-known/auth-config")
    methods = [m["id"] for m in r.json()["methods"]]
    check("auth-config 含 password", "password" in methods, str(methods))

    r = client.get("/.well-known/openid-configuration")
    check("discovery issuer 正确", r.json()["issuer"] == BASE, r.text[:80])

    print("\n[2] 注册（follow_tfv5，假服务允许）")
    reg = client.get("/api/auth/registration").json()
    check("注册策略判定为允许", reg["allowed"] is True, str(reg))

    username = f"alice{int(time.time()) % 100000}"
    r = client.post("/api/auth/register",
                    json={"username": username, "password": "platform-pass-123"})
    check("注册成功", r.status_code == 200, r.text[:200])
    check("下发 session cookie", "tf_session" in client.cookies)
    check("下发 csrf cookie", "tf_csrf" in client.cookies)
    token_csrf = client.cookies.get("tf_csrf")

    print("\n[3] 会话与 CSRF")
    r = client.get("/api/auth/me")
    check("me 返回当前用户", r.json()["user"]["username"] == username)

    r = client.post("/api/auth/logout")
    check("缺 CSRF 被拒", r.status_code == 403, str(r.status_code))

    r = client.post("/api/auth/logout", headers={"X-CSRF-Token": token_csrf})
    check("带 CSRF 登出成功", r.status_code == 200, r.text[:120])

    r = client.post("/api/auth/login",
                    json={"identifier": username, "password": "platform-pass-123"})
    check("重新登录成功", r.status_code == 200, r.text[:120])
    csrf = client.cookies.get("tf_csrf")

    print("\n[4] 绑定（走 TFV5 专用端点）")
    before = fake.get("/_debug/state").json()
    r = client.post("/api/connections/bind",
                    json={"identifier": "alice", "password": "alice-password"},
                    headers={"X-CSRF-Token": csrf})
    check("绑定成功", r.status_code == 200, r.text[:300])
    body = r.json().get("connection", {})
    check("走 platform 链路", body.get("channel") == "platform", str(body))
    check("tfv5_uid 正确", body.get("tfv5_uid") == 1001, str(body))

    after = fake.get("/_debug/state").json()
    check("TFV5 侧新增一条身份映射",
          len(after["identities"]) == len(before["identities"]) + 1,
          f"{len(before['identities'])} -> {len(after['identities'])}")
    check("专用端点未创建 TFV5 会话（关键）",
          len(after["sessions"]) == len(before["sessions"]),
          f"sessions {before['sessions']} -> {after['sessions']}")
    check("未走旧版 /auth/login", after["login_calls"] == before["login_calls"])

    r = client.get("/api/connections")
    conns = r.json()["connections"]
    check("连接列表有 1 条", len(conns) == 1, str(conns))
    check("legacy 才缓存 refresh token", conns[0]["has_cached_session"] is False, str(conns[0]))

    print("\n[5] 错误凭据")
    r = client.post("/api/connections/bind",
                    json={"identifier": "alice", "password": "wrong"},
                    headers={"X-CSRF-Token": csrf})
    check("错密码返回 401", r.status_code == 401, r.text[:200])
    check("错误码可读", r.json()["error"]["code"] == "tfv5_bad_credentials", r.text[:200])

    r = client.post("/api/connections/bind",
                    json={"identifier": "bob", "password": "bob-password"},
                    headers={"X-CSRF-Token": csrf})
    check("封禁账号被拒", r.status_code in (403, 409), r.text[:200])

    print("\n[6] 代授权 → ticket → external_token")
    r = client.post("/api/authorize/complete",
                    json={"client_id": "touchfish", "state": "abc123"},
                    headers={"X-CSRF-Token": csrf})
    check("complete 成功", r.status_code == 200, r.text[:200])
    ticket = r.json().get("ticket", "")
    check("ticket 非空", len(ticket) > 20)

    anon = httpx.Client(base_url=BASE, trust_env=False, timeout=10)
    r = anon.post("/api/auth/ticket", json={"ticket": ticket, "client_id": "touchfish"})
    check("换 token 成功", r.status_code == 200, r.text[:200])
    external = r.json().get("external_token", "")
    claims = jwt.decode(external, options={"verify_signature": False})
    check("iss 等于平台 issuer", claims["iss"] == BASE, str(claims.get("iss")))
    check("sub 是平台用户 id", isinstance(claims["sub"], str) and len(claims["sub"]) == 32)
    check("带 tfv5_uid", claims.get("tfv5_uid") == 1001, str(claims))

    # 按 kid 选公钥再做完整验签。轮换后 JWKS 里会有多把钥匙，
    # 玩具代码取 keys[0] 会误验，这里显式对齐 header.kid。
    header = jwt.get_unverified_header(external)
    matching = next((k for k in jwks["keys"] if k["kid"] == header.get("kid")), None)
    check("JWKS 含签发该 token 的 kid", matching is not None, str(header.get("kid")))
    pub = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(matching))
    payload = jwt.decode(external, pub, algorithms=["RS256"], issuer=BASE)
    check("公钥验签通过", payload["sub"] == claims["sub"])
    check("token 有效期 300s", payload["exp"] - payload["iat"] == 300,
          str(payload["exp"] - payload["iat"]))

    r = anon.post("/api/auth/ticket", json={"ticket": ticket, "client_id": "touchfish"})
    check("ticket 一次性", r.status_code == 409, r.text[:120])

    print("\n[7] 解绑")
    r = client.delete("/api/connections/main", headers={"X-CSRF-Token": csrf})
    check("解绑成功", r.status_code == 200, r.text[:200])
    final = fake.get("/_debug/state").json()
    check("TFV5 侧映射被删除", final["identities"] == [], str(final["identities"]))
    r = client.get("/api/connections")
    check("连接列表清空", r.json()["connections"] == [])

    print("\n[8] 未登录访问")
    r = anon.get("/api/connections")
    check("未登录 401", r.status_code == 401)

    print(f"\n通过 {ok_count} 项，失败 {fail_count} 项")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

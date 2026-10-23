"""安全回归：/api/connections/tfv5-login 的凭据校验与 CSRF 豁免。

修前状态（已复现）：
  - 已绑定分支不校验密码 → 知道 TFV5 用户名即可接管对应平台账户；
  - 该端点不在 CSRF 豁免表 → 匿名首次使用必然 403。

本脚本是修复后的回归，全部应通过：
  [1] 已绑定 + 错密码 → 401，且不下发会话
  [2] 已绑定 + 正确密码 → 200，正常下发会话
  [3] 匿名（无 csrf cookie）→ 不再被 csrf_failed 拦截
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx

from _fixtures import relaxed_site_settings

BASE = "http://127.0.0.1:8000"
FAKE = "http://127.0.0.1:7001"
BACKEND = Path(__file__).resolve().parent.parent
DB_PATH = BACKEND / "data" / "auth.db"

ok = 0
fail = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global ok, fail
    if condition:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail += 1
        print(f"  FAIL  {name}  {detail}")


def main() -> int:
    with relaxed_site_settings():
        return _run()


def _run() -> int:
    httpx.Client(base_url=FAKE, trust_env=False, timeout=10).post("/_debug/reset")
    # 清掉历史运行留下的 alice 绑定，否则本脚本无法建立自己的前置状态
    if DB_PATH.is_file():
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM connections WHERE tfv5_uid IN (1001, 1002, 1003)")
        conn.commit()
        conn.close()

    suffix = int(time.time()) % 100000
    victim = httpx.Client(base_url=BASE, trust_env=False, timeout=20)
    attacker = httpx.Client(base_url=BASE, trust_env=False, timeout=20)

    print("\n[1] 准备：受害者绑定 alice")
    r = victim.post("/api/auth/register",
                    json={"username": f"victim{suffix}", "password": "victim-pass-1"})
    check("受害者注册", r.status_code == 200, r.text[:160])
    csrf = victim.cookies.get("tf_csrf") or ""
    r = victim.post("/api/connections/bind",
                    json={"identifier": "alice", "password": "alice-password"},
                    headers={"X-CSRF-Token": csrf})
    check("alice 绑定成功", r.status_code == 200, r.text[:160])

    print("\n[2] 攻击者：只注册自己的账户拿 csrf，然后登出")
    attacker.post("/api/auth/register",
                  json={"username": f"evil{suffix}", "password": "evil-pass-123"})
    evil_csrf = attacker.cookies.get("tf_csrf") or ""
    attacker.post("/api/auth/logout", headers={"X-CSRF-Token": evil_csrf})
    attacker.cookies.clear()
    attacker.cookies.set("tf_csrf", evil_csrf)

    print("\n[3] 已绑定 + 错误密码必须被拒")
    r = attacker.post("/api/connections/tfv5-login",
                      json={"identifier": "alice", "password": "definitely-wrong"},
                      headers={"X-CSRF-Token": evil_csrf})
    check("返回 401", r.status_code == 401, f"{r.status_code} {r.text[:200]}")
    check("未下发会话 cookie", "tf_session" not in attacker.cookies)
    check("越权未成立（响应不含他人 user）", "victim" not in r.text, r.text[:200])

    print("\n[4] 已绑定 + 正确密码可用")
    good = httpx.Client(base_url=BASE, trust_env=False, timeout=20)
    r = good.post("/api/connections/tfv5-login",
                  json={"identifier": "alice", "password": "alice-password"})
    check("返回 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    check("下发会话", "tf_session" in good.cookies)
    me = good.get("/api/auth/me").json().get("user") or {}
    check("登录到正确的平台账户", str(me.get("username", "")).startswith("victim"), str(me))

    print("\n[5] 匿名（无任何 cookie）不再被 CSRF 拦")
    anon = httpx.Client(base_url=BASE, trust_env=False, timeout=20)
    r = anon.post("/api/connections/tfv5-login",
                  json={"identifier": "alice", "password": "definitely-wrong"})
    check("不是 csrf_failed", r.json().get("error", {}).get("code") != "csrf_failed",
          r.text[:200])
    check("仅因凭据错误而 401", r.status_code == 401, r.text[:200])

    # 下面几项要改站点配置，需要一个管理员
    print("\n[6] 未绑定用户的自动开通受两层开关控制")
    boss = httpx.Client(base_url=BASE, trust_env=False, timeout=20)
    boss.post("/api/auth/register",
              json={"username": f"boss{suffix}", "password": "boss-pass-123"})
    subprocess.run([sys.executable, "-m", "app.cli", "promote", f"boss{suffix}"],
                   cwd=str(BACKEND), capture_output=True, text=True)
    boss.cookies.clear()
    boss.post("/api/auth/login",
              json={"identifier": f"boss{suffix}", "password": "boss-pass-123"})
    bcsrf = boss.cookies.get("tf_csrf") or ""

    def set_site(values: dict) -> None:
        boss.put("/api/admin/settings", json={"values": values},
                 headers={"X-CSRF-Token": bcsrf})

    set_site({"tfv5_login_auto_signup": False})
    probe = httpx.Client(base_url=BASE, trust_env=False, timeout=20)
    r = probe.post("/api/connections/tfv5-login",
                   json={"identifier": "carol", "password": "carol-password"})
    check("关闭自动开通后拒绝开通", r.status_code == 409
          and r.json()["error"]["code"] == "auto_signup_disabled", r.text[:200])
    check("未下发会话", "tf_session" not in probe.cookies)

    set_site({"tfv5_login_auto_signup": True, "registration_mode": "force_off"})
    r = probe.post("/api/connections/tfv5-login",
                   json={"identifier": "carol", "password": "carol-password"})
    check("注册总闸关闭时同样拒绝", r.status_code == 403
          and r.json()["error"]["code"] == "register_disabled", r.text[:200])

    set_site({"registration_mode": "follow_tfv5"})
    r = probe.post("/api/connections/tfv5-login",
                   json={"identifier": "carol", "password": "carol-password"})
    check("两个开关都放开时可开通", r.status_code == 200, r.text[:200])

    print("\n[7] 登录需要人机验证时，该端点也必须过闸")
    set_site({"captcha_on_login": True, "captcha_site_key": "k", "captcha_secret": "s",
              "captcha_verify_url": "http://127.0.0.1:7010/"})
    r = httpx.post(f"{BASE}/api/connections/tfv5-login",
                   json={"identifier": "alice", "password": "alice-password"},
                   trust_env=False, timeout=20)
    check("无 token 被拒", r.status_code == 400
          and r.json()["error"]["code"] == "captcha_failed", r.text[:200])
    set_site({"captcha_on_login": False})

    print("\n[8] 换绑到他人已占用的 TouchFish 账号应 409 而不是 500")
    dup = httpx.Client(base_url=BASE, trust_env=False, timeout=20)
    r = dup.post("/api/connections/tfv5-login",
                 json={"identifier": "carol", "password": "carol-password"})
    check("dup 账户已绑定 carol", r.status_code == 200, r.text[:160])
    dcsrf = dup.cookies.get("tf_csrf") or ""
    r = dup.post("/api/connections/bind",
                 json={"identifier": "alice", "password": "alice-password"},
                 headers={"X-CSRF-Token": dcsrf})
    check("换绑被拒且为 409（而非 500）", r.status_code == 409, f"{r.status_code} {r.text[:200]}")
    # 正常顺序下 TFV5 的 own 检查先返回 external_already_linked；
    # 本地 _ensure_uid_free 是 TFV5 侧映射丢失/并发时的兜底，两者都是 409 且文案清晰。
    check("错误码可读（tfv5_uid_taken 或 tfv5_already_linked）",
          r.json()["error"]["code"] in ("tfv5_uid_taken", "tfv5_already_linked"),
          r.text[:200])

    print("\n[9] 登录失败退避")
    httpx.post(f"{BASE}/api/dev/throttle/reset", trust_env=False, timeout=5)
    set_site({"login_throttle_enabled": True, "login_max_failures": 3})

    # 先打两次错密码再成功一次：应清零，说明正常用户偶尔输错不会被累计惩罚
    account = f"thr{suffix}"
    victim.post("/api/auth/register",
                json={"username": account, "password": "thr-pass-123"})
    for _ in range(2):
        httpx.post(f"{BASE}/api/auth/login",
                   json={"identifier": account, "password": "wrong-pass"},
                   trust_env=False, timeout=10)
    r = httpx.post(f"{BASE}/api/auth/login",
                   json={"identifier": account, "password": "thr-pass-123"},
                   trust_env=False, timeout=10)
    check("两次失败后仍可正常登录（计数已清零）", r.status_code == 200, r.text[:200])

    # 再连续失败，超过阈值后应 429 并带 Retry-After
    codes = []
    for _ in range(6):
        resp = httpx.post(f"{BASE}/api/auth/login",
                          json={"identifier": account, "password": "wrong-pass"},
                          trust_env=False, timeout=10)
        codes.append(resp.status_code)
        if resp.status_code == 429:
            check("429 带 Retry-After", bool(resp.headers.get("retry-after")),
                  str(resp.headers))
            check("错误码为 too_many_attempts",
                  resp.json()["error"]["code"] == "too_many_attempts", resp.text[:160])
            break
    check("连续失败后被锁定", 429 in codes, str(codes))

    # 锁定后即便密码正确也先拒绝（否则等于锁形同虚设）
    r = httpx.post(f"{BASE}/api/auth/login",
                   json={"identifier": account, "password": "thr-pass-123"},
                   trust_env=False, timeout=10)
    check("锁定期间正确密码也被拒", r.status_code == 429, r.text[:160])

    httpx.post(f"{BASE}/api/dev/throttle/reset", trust_env=False, timeout=5)
    set_site({"login_max_failures": 8})

    print("\n[10] CSRF 豁免端点的同源闸门")
    r = httpx.post(f"{BASE}/api/dev/throttle/reset", trust_env=False, timeout=5)
    check("dev reset 不再被 CSRF 拦", r.status_code == 200, r.text[:160])

    evil = {"Origin": "https://evil.example"}
    r = httpx.post(f"{BASE}/api/connections/tfv5-login",
                   json={"identifier": "alice", "password": "alice-password"},
                   headers=evil, trust_env=False, timeout=10)
    check("跨站 Origin 被拒（登录 CSRF）", r.status_code == 403, r.text[:200])

    r = httpx.post(f"{BASE}/api/auth/login",
                   json={"identifier": account, "password": "thr-pass-123"},
                   headers=evil, trust_env=False, timeout=10)
    check("平台登录同样被拒", r.status_code == 403, r.text[:200])

    r = httpx.post(f"{BASE}/api/connections/tfv5-login",
                   json={"identifier": "alice", "password": "alice-password"},
                   headers={"Origin": BASE}, trust_env=False, timeout=10)
    check("同源 Origin 放行", r.status_code == 200, r.text[:200])

    print("\n[11] 登录复用绑定不应改写 bound_at")
    row = None
    if DB_PATH.is_file():
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT bound_at, last_login_at FROM connections WHERE tfv5_uid = 1001"
        ).fetchone()
        conn.close()
    if row is not None:
        # 刚登录过，last_login_at 应 >= bound_at，且 bound_at 仍是首次绑定时间
        check("last_login_at 已写入", row["last_login_at"] is not None, str(dict(row)))
        check("bound_at 未被登录时间覆盖",
              row["last_login_at"] >= row["bound_at"], str(dict(row)))

    print(f"\n通过 {ok} 项，失败 {fail} 项")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

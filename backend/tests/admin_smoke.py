"""管理员链路冒烟：注册 → CLI 授予 → 管理接口可用 → 普通用户被拒。"""
from __future__ import annotations

import subprocess
import sys

from _fixtures import relaxed_site_settings
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
BACKEND = Path(__file__).resolve().parent.parent
PY = BACKEND / ".venv" / "Scripts" / "python.exe"

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


def cli(*args: str) -> tuple[int, str]:
    result = subprocess.run(
        [str(PY), "-m", "app.cli", *args],
        cwd=str(BACKEND), capture_output=True, text=True, encoding="utf-8",
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    # 站点若开着验证码/邮箱验证，本测试注册不出账号；夹具会在结束后原样还原配置
    with relaxed_site_settings():
        return _run()


def _run() -> int:
    suffix = int(time.time()) % 100000
    admin_name = f"adm{suffix}"
    plain_name = f"usr{suffix}"

    print("\n[1] 注册两个账号")
    admin_client = httpx.Client(base_url=BASE, trust_env=False, timeout=20)
    plain_client = httpx.Client(base_url=BASE, trust_env=False, timeout=20)
    r = admin_client.post("/api/auth/register",
                          json={"username": admin_name, "password": "admin-pass-123"})
    check("管理员候选注册成功", r.status_code == 200, r.text[:200])
    r = plain_client.post("/api/auth/register",
                          json={"username": plain_name, "password": "plain-pass-123"})
    check("普通用户注册成功", r.status_code == 200, r.text[:200])

    print("\n[2] 未授权时管理接口应 403")
    r = admin_client.get("/api/admin/overview")
    check("普通用户访问 /api/admin 被拒", r.status_code == 403, r.text[:160])
    check("错误码为 forbidden",
          r.json().get("error", {}).get("code") == "forbidden", r.text[:160])

    print("\n[3] CLI 授予管理员")
    code, out = cli("promote", admin_name)
    check("promote 退出码 0", code == 0, out[:200])
    check("输出提到已授予", "已授予" in out, out[:200])

    code, out = cli("list")
    check("list 能列出用户", admin_name in out, out[:300])
    check("list 显示角色列", "admin" in out, out[:300])

    print("\n[4] 重新登录后管理接口可用")
    admin_client.cookies.clear()
    r = admin_client.post("/api/auth/login",
                          json={"identifier": admin_name, "password": "admin-pass-123"})
    check("管理员登录成功", r.status_code == 200, r.text[:200])
    r = admin_client.get("/api/admin/overview")
    check("overview 返回 200", r.status_code == 200, r.text[:200])
    data = r.json() if r.status_code == 200 else {}
    check("overview 含 stats", "stats" in data, str(data)[:200])
    check("管理员计数 >= 1", data.get("stats", {}).get("admins", 0) >= 1, str(data.get("stats")))
    check("overview 含用户列表", any(u["username"] == admin_name for u in data.get("users", [])))
    check("overview 含实例", isinstance(data.get("instances"), list))
    check("overview 含 kid", bool(data.get("keys", {}).get("active_kid")))

    print("\n[5] 角色变更需要管理员")
    target = next(u for u in data["users"] if u["username"] == plain_name)
    csrf = admin_client.cookies.get("tf_csrf") or ""
    r = plain_client.post(f"/api/admin/users/{target['id']}/role",
                          json={"role": "admin"},
                          headers={"X-CSRF-Token": plain_client.cookies.get("tf_csrf") or ""})
    check("普通用户改角色被拒", r.status_code == 403, r.text[:160])

    print("\n[6] 管理员可以停用普通用户")
    r = admin_client.post(f"/api/admin/users/{target['id']}/status",
                          json={"status": "suspended"},
                          headers={"X-CSRF-Token": csrf})
    check("停用成功", r.status_code == 200, r.text[:200])

    fresh = httpx.Client(base_url=BASE, trust_env=False, timeout=20)
    r = fresh.post("/api/auth/login",
                   json={"identifier": plain_name, "password": "plain-pass-123"})
    check("被停用账户无法登录", r.status_code == 403, r.text[:200])

    r = admin_client.post(f"/api/admin/users/{target['id']}/status",
                          json={"status": "active"},
                          headers={"X-CSRF-Token": csrf})
    check("恢复成功", r.status_code == 200, r.text[:200])

    print("\n[7] 自我保护")
    me = data["me"]["id"]
    r = admin_client.post(f"/api/admin/users/{me}/role",
                          json={"role": "user"},
                          headers={"X-CSRF-Token": csrf})
    check("不能取消自己的管理员权限", r.status_code == 409, r.text[:200])
    r = admin_client.post(f"/api/admin/users/{me}/status",
                          json={"status": "suspended"},
                          headers={"X-CSRF-Token": csrf})
    check("不能停用自己", r.status_code == 409, r.text[:200])

    print("\n[8] CLI 拒绝降级最后一个管理员")
    admins = data["stats"]["admins"]
    code, out = cli("demote", admin_name)
    if admins <= 1:
        check("最后一个管理员不可降级", code == 1, out[:200])
    else:
        # 库里还有别的管理员（历史测试遗留），此时降级本应成功；
        # 校验后立刻恢复，避免破坏其他用例的前置条件。
        check("存在多个管理员时允许降级", code == 0, out[:200])
        cli("promote", admin_name)
        check("恢复后仍是管理员", cli("list")[1].count("admin") >= 2, "")

    print("\n[9] 静态资源")
    r = httpx.get(f"{BASE}/logo.png", trust_env=False, timeout=10)
    check("logo 可访问", r.status_code == 200 and r.headers.get("content-type", "").startswith("image"),
          f"{r.status_code} {r.headers.get('content-type')}")
    r = httpx.get(f"{BASE}/admin", trust_env=False, timeout=10)
    check("SPA 路由 /admin 可访问", r.status_code == 200 and 'id="root"' in r.text)

    print(f"\n通过 {ok} 项，失败 {fail} 项")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

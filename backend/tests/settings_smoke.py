"""站点配置 / 邮箱验证 / 人机验证 冒烟。

自带一个假的 siteverify 服务，用来验证 captcha 校验链路而不依赖外网。
运行前需：本服务在 8000、假 TFV5 在 7001。
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import httpx

BASE = "http://127.0.0.1:8000"
BACKEND = Path(__file__).resolve().parent.parent
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
DB_PATH = BACKEND / "data" / "auth.db"

ok = 0
fail = 0


from _fixtures import restore_settings, snapshot_settings, wipe_settings  # noqa: E402


def check(name: str, condition: bool, detail: str = "") -> None:
    global ok, fail
    if condition:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail += 1
        print(f"  FAIL  {name}  {detail}")


# ---------- 假 siteverify ----------

CAPTCHA_CALLS: list[dict] = []


class VerifyHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length).decode("utf-8")
        form = {k: v[0] for k, v in parse_qs(raw).items()}
        CAPTCHA_CALLS.append(form)
        # 与真实 siteverify 一致：Secret 不对时报 invalid-input-secret，
        # token 不对时报 invalid-input-response，两者都是 HTTP 400。
        if form.get("secret") != "test-secret":
            success, codes = False, ["invalid-input-secret"]
        elif form.get("response") != "good-token":
            success, codes = False, ["invalid-input-response"]
        else:
            success, codes = True, []
        body = json.dumps({"success": success, "error-codes": codes})
        status = 200 if success else 400
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):  # 静音
        return


def start_fake_siteverify() -> HTTPServer:
    server = HTTPServer(("127.0.0.1", 7010), VerifyHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def cli(*args: str) -> tuple[int, str]:
    result = subprocess.run([str(PY), "-m", "app.cli", *args], cwd=str(BACKEND),
                            capture_output=True, text=True, encoding="utf-8")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    suffix = int(time.time()) % 100000
    siteverify = start_fake_siteverify()
    admin = httpx.Client(base_url=BASE, trust_env=False, timeout=20)
    anon = httpx.Client(base_url=BASE, trust_env=False, timeout=20)
    original_settings = snapshot_settings()
    # 落一份磁盘备份：万一进程被强杀，配置还能手工还原
    backup = BACKEND / "data" / "settings_snapshot.json"
    backup.write_text(json.dumps(original_settings, ensure_ascii=False, indent=2), encoding="utf-8")
    wipe_settings()

    try:
        print("\n[1] 公开配置")
        r = anon.get("/api/site")
        check("/api/site 200", r.status_code == 200, r.text[:200])
        public = r.json()
        check("含 site_name", isinstance(public.get("site_name"), str), str(public)[:160])
        check("含 registration.allowed", "allowed" in public.get("registration", {}))
        check("未启用时不下发验证码 site_key",
              public["captcha"]["enabled"] is False and public["captcha"]["site_key"] == "")
        check("不泄露 secret", "captcha_secret" not in json.dumps(public))

        print("\n[2] 准备管理员")
        admin_name = f"cfg{suffix}"
        r = admin.post("/api/auth/register",
                       json={"username": admin_name, "password": "cfg-pass-123"})
        check("注册管理员候选", r.status_code == 200, r.text[:200])
        code, out = cli("promote", admin_name)
        check("CLI 授权", code == 0, out[:160])
        admin.cookies.clear()
        admin.post("/api/auth/login",
                   json={"identifier": admin_name, "password": "cfg-pass-123"})
        csrf = admin.cookies.get("tf_csrf") or ""

        print("\n[3] 权限")
        r = anon.get("/api/admin/settings")
        check("普通/未登录读配置被拒", r.status_code in (401, 403), r.text[:120])
        r = admin.get("/api/admin/settings")
        check("管理员读配置成功", r.status_code == 200, r.text[:200])
        spec = r.json().get("_spec", [])
        check("返回配置项清单", len(spec) >= 15, str(len(spec)))
        check("secret 项不回显", r.json().get("smtp_password") == ""
              and "has_smtp_password" in r.json())

        print("\n[4] 配置校验")
        # 先清空上一次运行可能残留的邮件配置，保证"半配置被拒"这条断言可重复
        admin.put("/api/admin/settings",
                  json={"values": {"email_verification": False,
                                   "smtp_host": "", "smtp_from": "",
                                   "captcha_enabled": False, "captcha_on_login": False,
                                   "captcha_site_key": "", "captcha_secret": "",
                                   "captcha_verify_url": ""}},
                  headers={"X-CSRF-Token": csrf})
        r = admin.put("/api/admin/settings", json={"values": {"nope": 1}},
                      headers={"X-CSRF-Token": csrf})
        check("未知键被拒", r.status_code == 400, r.text[:160])
        r = admin.put("/api/admin/settings",
                      json={"values": {"email_verification": True}},
                      headers={"X-CSRF-Token": csrf})
        check("开启邮箱验证但没配 SMTP 被拒", r.status_code == 400, r.text[:200])
        check("错误信息指出具体字段",
              r.json()["error"]["code"] == "invalid_setting", r.text[:200])
        r = admin.put("/api/admin/settings",
                      json={"values": {"token_ttl": 10}},
                      headers={"X-CSRF-Token": csrf})
        check("超范围整数被拒", r.status_code == 400, r.text[:160])

        print("\n[5] 站点基础配置生效")
        r = admin.put("/api/admin/settings",
                      json={"values": {"site_name": "摸鱼认证", "announcement": "维护中，请稍后"}},
                      headers={"X-CSRF-Token": csrf})
        check("保存站点名", r.status_code == 200, r.text[:200])
        r = anon.get("/api/site")
        check("/api/site 反映新站点名", r.json()["site_name"] == "摸鱼认证", r.text[:160])
        check("/api/site 反映公告", r.json()["announcement"] == "维护中，请稍后")
        r = anon.get("/.well-known/auth-config")
        check("auth-config 用站点名", r.json()["site_name"] == "摸鱼认证", r.text[:200])

        print("\n[6] 邮箱验证流程")
        r = admin.put("/api/admin/settings",
                      json={"values": {"email_verification": True,
                                       "smtp_host": "smtp.example.com",
                                       "smtp_from": "noreply@example.com"}},
                      headers={"X-CSRF-Token": csrf})
        check("配置完整后开启成功", r.status_code == 200, r.text[:200])

        r = anon.post("/api/auth/register",
                      json={"username": f"noem{suffix}", "password": "mail-pass-123"})
        check("未填邮箱被拒", r.status_code == 400 and r.json()["error"]["code"] == "email_required",
              r.text[:160])

        email = f"test{suffix}@example.com"
        username = f"mail{suffix}"
        r = anon.post("/api/auth/register",
                      json={"username": username, "password": "mail-pass-123", "email": email})
        check("注册返回待验证", r.status_code == 202, r.text[:200])
        pending = r.json()
        check("返回 verification_id", bool(pending.get("verification_id")))
        check("邮箱已打码", "*" in pending.get("email", ""), pending.get("email", ""))

        r = anon.post("/api/auth/login",
                      json={"identifier": username, "password": "mail-pass-123"})
        check("未验证无法登录", r.status_code == 403
              and r.json()["error"]["code"] == "email_unverified", r.text[:160])

        outbox = httpx.get(f"{BASE}/api/dev/outbox", trust_env=False, timeout=5)
        check("开发收件箱可用", outbox.status_code == 200, outbox.text[:120])
        mails = outbox.json().get("mails", [])
        target = next((m for m in reversed(mails) if m["to"] == email), None)
        check("收到验证邮件", target is not None, str(len(mails)))
        code_in_mail = None
        if target:
            match = re.search(r"\b(\d{6})\b", target["body"])
            code_in_mail = match.group(1) if match else None
        check("邮件含 6 位验证码", code_in_mail is not None, str(target)[:160])

        r = anon.post("/api/auth/verify-email",
                      json={"verification_id": pending["verification_id"], "code": "000000"})
        check("错误验证码被拒", r.status_code == 400, r.text[:160])

        r = anon.post("/api/auth/verify-email",
                      json={"verification_id": pending["verification_id"], "code": code_in_mail})
        check("正确验证码通过", r.status_code == 200, r.text[:200])
        check("验证后即登录", "tf_session" in anon.cookies)
        check("账户状态 active", r.json()["user"]["status"] == "active", r.text[:200])

        r = anon.post("/api/auth/verify-email",
                      json={"verification_id": pending["verification_id"], "code": code_in_mail})
        check("验证码一次性", r.status_code == 400, r.text[:160])

        # 固化该用户的会话快照，供 [9] 验证强制下线（后面 anon 会被复用到别的账号）
        victim_client = httpx.Client(base_url=BASE, trust_env=False, timeout=10)
        victim_client.cookies.update(anon.cookies)
        r = victim_client.get("/api/auth/me")
        check("受害者会话已建立", r.json().get("user") is not None, r.text[:160])

        admin.put("/api/admin/settings", json={"values": {"email_verification": False}},
                  headers={"X-CSRF-Token": csrf})

        print("\n[7] 人机验证")
        r = admin.put("/api/admin/settings",
                      json={"values": {"captcha_enabled": True}},
                      headers={"X-CSRF-Token": csrf})
        check("只开开关不给密钥被拒", r.status_code == 400, r.text[:200])

        r = admin.put("/api/admin/settings",
                      json={"values": {"captcha_enabled": True,
                                       "captcha_provider": "turnstile",
                                       "captcha_site_key": "test-site-key",
                                       "captcha_secret": "test-secret",
                                       "captcha_verify_url": "http://127.0.0.1:7010/"}},
                      headers={"X-CSRF-Token": csrf})
        check("配置完整后开启成功", r.status_code == 200, r.text[:200])
        r = anon.get("/api/site")
        check("公开配置下发 site_key", r.json()["captcha"]["site_key"] == "test-site-key",
              r.text[:160])
        check("公开配置仍不含 secret", "test-secret" not in r.text)

        r = anon.post("/api/auth/register",
                      json={"username": f"cap{suffix}", "password": "cap-pass-123"})
        check("缺 captcha token 被拒", r.status_code == 400
              and r.json()["error"]["code"] == "captcha_failed", r.text[:160])

        r = anon.post("/api/auth/register",
                      json={"username": f"cap{suffix}", "password": "cap-pass-123",
                            "captcha_token": "bad-token"})
        check("错误 captcha token 被拒", r.status_code == 400, r.text[:160])
        check("拒绝原因透出而不是只说'未通过'",
              "token" in r.json()["error"]["message"], r.text[:200])

        r = anon.post("/api/auth/register",
                      json={"username": f"cap{suffix}", "password": "cap-pass-123",
                            "captcha_token": "good-token"})
        check("正确 captcha token 通过", r.status_code == 200, r.text[:200])
        check("siteverify 收到 secret 与 remoteip",
              any(c.get("secret") == "test-secret" for c in CAPTCHA_CALLS),
              str(CAPTCHA_CALLS[-1:] if CAPTCHA_CALLS else []))

        admin.put("/api/admin/settings", json={"values": {"captcha_enabled": False}},
                  headers={"X-CSRF-Token": csrf})

        print("\n[8] 验证码配置自检")
        # 开回验证码，分别用正确/错误的 Secret 探测，应能区分原因
        admin.put("/api/admin/settings",
                  json={"values": {"captcha_enabled": True}},
                  headers={"X-CSRF-Token": csrf})
        r = admin.post("/api/admin/captcha/test", headers={"X-CSRF-Token": csrf})
        check("自检接口可用", r.status_code == 200, r.text[:200])
        probe = r.json()
        check("正确 Secret 返回 token 无效", "invalid-input-response" in probe["codes"],
              str(probe.get("codes")))
        check("给出'配置正确'提示", "配置正确" in probe.get("hint", ""), probe.get("hint", ""))

        admin.put("/api/admin/settings",
                  json={"values": {"captcha_secret": "wrong-secret"}},
                  headers={"X-CSRF-Token": csrf})
        r = admin.post("/api/admin/captcha/test", headers={"X-CSRF-Token": csrf})
        wrong = r.json()
        check("错误 Secret 返回 invalid-input-secret",
              "invalid-input-secret" in wrong["codes"], str(wrong.get("codes")))
        check("指出是 Secret 的问题", "Secret" in wrong.get("hint", ""), wrong.get("hint", ""))

        admin.put("/api/admin/settings",
                  json={"values": {"captcha_secret": "test-secret"}},
                  headers={"X-CSRF-Token": csrf})
        admin.put("/api/admin/settings", json={"values": {"captcha_enabled": False}},
                  headers={"X-CSRF-Token": csrf})

        print("\n[9] 审计日志")
        r = admin.get("/api/admin/audit?limit=50")
        check("审计日志可读", r.status_code == 200, r.text[:200])
        events = [row["event"] for row in r.json().get("entries", [])]
        check("记录到 admin.settings", "admin.settings" in events, str(events[:8]))
        check("记录到 user.verified", "user.verified" in events, str(events[:8]))
        check("不记录敏感值",
              all("test-secret" not in (row.get("detail") or "")
                  for row in r.json().get("entries", [])))

        print("\n[10] 强制下线")
        r = admin.get("/api/admin/overview")
        victim = next(u for u in r.json()["users"] if u["username"] == username)
        r = admin.post(f"/api/admin/users/{victim['id']}/logout-all",
                       headers={"X-CSRF-Token": csrf})
        check("强制下线成功", r.status_code == 200 and r.json()["revoked"] >= 1, r.text[:200])
        r = victim_client.get("/api/auth/me")
        check("被下线后会话失效", r.json()["user"] is None, r.text[:160])

    finally:
        # 整表还原：不能只还原自己改过的那几项，否则会漏（例如 captcha_verify_url）
        restore_settings(original_settings)
        if backup.is_file():
            backup.unlink()
        siteverify.shutdown()

    print(f"\n通过 {ok} 项，失败 {fail} 项")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

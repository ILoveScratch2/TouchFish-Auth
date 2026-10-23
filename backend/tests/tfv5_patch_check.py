"""对 TFV5_server 补丁的静态验证。

不做运行时启动（那需要占用真实实例的 res/<port> 数据），
只确认四处改动确实落在代码里、且没有破坏既有结构。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TFV5 = Path("D:/TouchFish-V5/TFV5_server")
sys.path.insert(0, str(TFV5))

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
    web = (TFV5 / "web.py").read_text(encoding="utf-8")
    main_py = (TFV5 / "main.py").read_text(encoding="utf-8")

    print("\n[1] 新端点")
    check("platform_bind 路由", '@api("/auth/platform/bind", methods=["POST"])' in web)
    check("platform_unbind 路由", '@api("/auth/platform/unbind", methods=["POST"])' in web)
    check("platform_status 路由", '@app.route("/auth/platform/status")' in web)
    check("状态端点用明文 GET（不是 @api）",
          '@app.route("/auth/platform/status")' in web and
          '@api("/auth/platform/status"' not in web)

    print("\n[2] 绑定不建会话（核心约束）")
    # 截取 platform_bind 函数体，确认内部没有会话创建调用
    match = re.search(r"def platform_bind\(req\):(.*?)\n    @api\(\"/auth/platform/unbind\"",
                      web, re.S)
    body = match.group(1) if match else ""
    check("找到函数体", bool(body))
    check("不调用 create_session_for_user", "create_session_for_user" not in body)
    check("不调用 issue_token", "issue_token" not in body)
    check("不写 auth_devices", "upsert_device" not in body)
    check("调用了 verify_user", "verify_user" in body)
    check("调用了 bind_identity", "bind_identity" in body)

    print("\n[3] unbind 不吊销全部设备")
    match = re.search(r"def platform_unbind\(req\):(.*?)\n    @app.route", web, re.S)
    body = match.group(1) if match else ""
    check("不调用 bump_auth_version", "bump_auth_version" not in body, body[:120])

    print("\n[4] 准入控制")
    check("有 IP 白名单函数", "def platform_caller_allowed" in web)
    check("用 ipaddress 解析 CIDR", "ipaddress.ip_network" in web)
    check("共享令牌用恒时比较", "hmac.compare_digest" in web)
    check("before_request 里前置拦截", 'if flask_request.path.startswith(PLATFORM_PREFIX)' in web)
    check("拦截在限流之前",
          web.index("if not platform_caller_allowed(cfg)") <
          web.index("if not limiter.is_allowed(ip, endpoint)"))

    print("\n[5] /info 下发")
    for field in ("external_auth_url", "platform_auth_enabled", "allow_register"):
        check(f"/info 含 {field}", f'"{field}"' in web)

    print("\n[6] 注册开关")
    check("register 拦截 allow_register", 'if not cfg.get("allow_register", True):' in web)
    check("返回 register_disabled", '"error": "register_disabled"' in web)

    print("\n[7] 配置与管理端")
    spec = (TFV5 / "config_utils.py").read_text(encoding="utf-8")
    for key in ("allow_register", "external_auth_url", "platform_auth_enabled",
                "platform_auth_issuer", "platform_auth_allow_ips",
                "platform_auth_shared_token"):
        check(f"SETTINGS_SPEC 含 {key}", f'"key": "{key}"' in spec)
    for key in ("external_auth_url", "platform_auth_allow_ips", "platform_auth_shared_token"):
        check(f"管理端可写 {key}", f'if "{key}" in req:' in web)

    print("\n[8] 默认值与限流")
    for key in ("allow_register", "external_auth_url", "platform_auth_enabled"):
        check(f"create_new_server 默认含 {key}", f'"{key}" :' in main_py)
    check("平台端点有独立限流配额", '"/auth/platform/bind" : {"requests":' in main_py)

    print("\n[9] 错误码")
    errors = (TFV5 / "error_codes.py").read_text(encoding="utf-8")
    check("REGISTER_DISABLED", "REGISTER_DISABLED" in errors)
    check("PLATFORM_NOT_CONFIGURED", "PLATFORM_NOT_CONFIGURED" in errors)

    print("\n[10] URL 校验（防 javascript: 注入）")
    check("external_auth_url 限定 http(s)",
          'value.startswith("http://") or value.startswith("https://")' in web)

    print(f"\n通过 {ok} 项，失败 {fail} 项")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

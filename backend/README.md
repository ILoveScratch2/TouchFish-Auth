# TouchFish Auth (BACKEND)

FastAPI 实现的 TouchFish Auth 后端服务。
整个项目请参考主 [README](../README.md)。


## 本地启动

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS / Linux

cp .env.example .env        # 需要填 AUTH_BASE_URL 与 AUTH_MASTER_KEY
AUTH_DEV_MAIL=1 .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`AUTH_MASTER_KEY` 生成：

```bash
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
```

启动时若 `../frontend/dist` 不存在，将只提供 API 服务，不提供前端。

## 环境变量

完整清单与注释见 [.env.example](.env.example)。

| 变量 | 说明 |
|---|---|
| `AUTH_BASE_URL` | 决定 issuer、JWKS 地址、第三方 OAuth 回调地址，反代后写公网 HTTPS 地址 |
| `AUTH_ISSUER` | 留空等于 `AUTH_BASE_URL`。改它要同步改 TF `jwt_external_issuers[].iss` |
| `AUTH_COOKIE_SECURE` | 本地 http 填写 `0` |
| `AUTH_TRUST_PROXY` | 默认不使用 `X-Forwarded-For`，优先使用 uvicorn `--proxy-headers --forwarded-allow-ips` |
| `AUTH_ALLOW_REGISTRATION` | 运行时可修改 |

## 命令行

```bash
.venv/Scripts/python -m app.cli list
.venv/Scripts/python -m app.cli promote <username>
.venv/Scripts/python -m app.cli demote <username>
.venv/Scripts/python -m app.cli instances
```

管理员只能通过本机 CLI 授予。

## 常见错误码

| 码 | 常见原因 |
|---|---|
| `csrf_failed` | 非 GET 请求没带 `X-CSRF-Token` 或跨站 Origin |
| `external_token_invalid` | TFV5 的 `jwt_external_issuers` 未包含该 issuer / 本地 http 未开 `allow_insecure_http` |
| `provider_already_bound` | 该第三方账号已属于另一个平台账号 |
| `last_login_method` | 没有密码且只有一条第三方绑定 |
| `register_disabled` | `registration_mode=force_off` |
| `mail_failed` | 未配 SMTP，调试可设置 `AUTH_DEV_MAIL=1`，查看本地邮件可通过 `/api/dev/outbox` |

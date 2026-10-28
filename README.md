# TouchFish Auth

*外部登录平台。为 TouchFish V5 签发外部 JWT（RS256 + JWKS）*


- 后端：Python 3.11+ / FastAPI / SQLite  
   - 可参考[backend/README.md](backend/README.md)
- 前端：React 19 + TypeScript + Tailwind 3.4 + Radix UI  
  - 可参考[frontend/README.md](frontend/README.md)


## 开始

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # 虚拟环境，可不使用
pip install -r requirements.txt
cp .env.example .env                                 # 填 AUTH_BASE_URL 与 AUTH_MASTER_KEY
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173 （/api 与 /.well-known 已代理到 8000）
npm run build      # 产物给后端托管
```

`AUTH_BASE_URL` 与 `AUTH_MASTER_KEY` 必填。

## 管理员

管理员只能由本机命令授予：

```bash
cd backend
.venv/Scripts/python -m app.cli list              # 列出用户
.venv/Scripts/python -m app.cli promote alice     # 授予
.venv/Scripts/python -m app.cli demote alice      # 收回
.venv/Scripts/python -m app.cli instances         # 列出 TFV5 实例
```

授予后该用户**重新登录**（或刷新页面）

## Testing


可设置环境变量 `AUTH_DEV_MAIL=1` 来启用开发模式下的邮件功能，便于测试密码重置等功能。（使用内部 API `/api/dev/outbox` 获取邮件内容）

### Captcha

<summary>Turnstile</summary>
<details>
<summary>Test Key</summary>

Turnstile 公开测试密钥：

| 用途 | Site Key | Secret |
|---|---|---|
| 永远通过 | `1x00000000000000000000AA` | `1x0000000000000000000000000000000AA` |
| 永远拦截 | `2x00000000000000000000AB` | `2x0000000000000000000000000000000AA` |

两者必须成对使用。

</details>

<summary>hCaptcha</summary>
<details>
<summary>Test</summary>
请参阅 [hCaptcha 官方文档](https://docs.hcaptcha.com/) 获取测试密钥和配置方法。


TouchFish-Auth 推荐使用 Turnstile 作为人机验证方案。


</details>



## 配置

使用管理员权限账户登入后台修改 TouchFish-Auth 配置。

### TouchFish V5 Server 配置

写入 `res/<port>/config.json`：

<summary>示例配置</summary>
<details>
<summary>Config</summary>

```json
{
  "allow_register": true,
  "external_auth_url": "http://127.0.0.1:8000",
  "platform_auth_enabled": true,
  "platform_auth_issuer": "http://127.0.0.1:8000",
  "platform_auth_allow_ips": "127.0.0.1,::1",
  "platform_auth_shared_token": "<openssl rand -hex 32>",
  "jwt_external_issuers": [{
    "iss": "http://127.0.0.1:8000",
    "algorithms": ["RS256"],
    "audience": "touchfish",
    "jwks_uri": "http://127.0.0.1:8000/.well-known/jwks.json",
    "require_exp": true,
    "allow_auto_create": false,
    "allow_insecure_http": true
  }]
}
```

</details>


注意：

- 生产环境 `iss` 必须是公网 HTTPS，且与 `AUTH_ISSUER` **完全一致**（含端口、不含末尾斜杠）
- 多实例部署配 `audience`：平台侧实例的 `audience` 与服务器侧
  `jwt_external_issuers[].audience` 需成对填写
- 本地测试使用 `127.0.0.1` 作为地址，且需要加入 `"allow_insecure_http": true`。

### OAuth Client

本平台可以作为 **OAuth client**，接任意标准的 OAuth2 / OIDC 平台（GitHub 等）。

在后台 第三方登录（`/admin/oauth`）里可添加新的平台。


回调地址在 OAuth 平台上配置为：

```
{AUTH_BASE_URL}/api/auth/oauth/{provider_key}/callback
```

注意：未验证邮箱无法完成第三方登录绑定或注册。


### OAuth Server

本平台同时可以作为 **OIDC 授权服务器**。

| 端点 | 用途 |
|---|---|
| `/.well-known/openid-configuration` | 发现文档 |
| `/authorize` | 授权端点，带 `response_type=code` 时进入同意页 |
| `/token` | 授权码 / 刷新令牌获得 token |
| `/api/userinfo` | Bearer 访问令牌获得用户声明 |
| `/.well-known/jwks.json` | id_token 验签公钥 |

注意：

- 公开客户端（如公共 Client）不使用 secret，使用**强制 PKCE + S256**。机密客户端（Confidential，如需要验证的服务器）可用 `client_secret`（可使用 basic 或 post）
- 回调地址不支持通配，请配置完整准确 URL
- TFV5 只接受 `token_use` 为空或为 `tfv5` 的令牌，第三方 OAuth 平台无法通过该 OAuth 登录 TouchFish V5。需要第三方登录 TouchFish V5 时需使用授权客户端流程（详情参考源代码）

## 限制

- 客户端 Web 端暂不支持外部登录闭环（浏览器没有 InAppWebView 的 JS 桥）注：OAuth 仍然可用，但无法完成自动传回。

- 无国际化（注意到 TouchFish V5 Server 与 TouchFish Auth 仅提供简体中文，TouchFish Client 提供翻译（实则只是为了玩）
- 不支持需要 PKCE 强制、JWT 客户端断言、或用户资料必须 POST 的 OAuth 平台；
- OAuth 不提供 implicit、client_credentials、登出与令牌撤销，将来也不会支持这些功能。

## License

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE) 文件。

# TouchFish Auth

外部登录平台。为 TouchFish V5 签发外部 JWT（RS256 + JWKS），


- 后端：Python 3.11+ / FastAPI / SQLite
- 前端：React 19 + TypeScript + Tailwind 3.4 + Radix


## 快速开始

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r requirements.txt
cp .env.example .env                                 # 填 AUTH_BASE_URL 与 AUTH_MASTER_KEY
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173，/api 与 /.well-known 已代理到 8000
npm run build      # 产物给后端托管
```

`AUTH_BASE_URL` 与 `AUTH_MASTER_KEY` 是必填项，缺失时启动直接报错并给出生成命令。
仓库里**没有任何生产地址默认值** —— 按约定，地址在部署时确定。

## 管理员

**没有"第一个注册用户自动成为管理员"这类隐式规则**（部署顺序会被人利用）。
管理员只能由本机命令授予：

```bash
cd backend
.venv/Scripts/python -m app.cli list              # 列出用户与角色
.venv/Scripts/python -m app.cli promote alice     # 授予管理员
.venv/Scripts/python -m app.cli demote alice      # 收回（最后一个管理员会被拒绝）
.venv/Scripts/python -m app.cli instances         # 列出 TFV5 实例
```

授予后该用户**重新登录**（或刷新页面）



### 使用 Cloudflare 测试密钥

Turnstile 提供一对公开测试密钥，可以在不注册域名的情况下联调：

| 用途 | Site Key | Secret |
|---|---|---|
| 永远通过 | `1x00000000000000000000AA` | `1x0000000000000000000000000000000AA` |
| 永远拦截 | `2x00000000000000000000AB` | `2x0000000000000000000000000000000AA` |

两者必须成对使用。混用（例如拿测试 sitekey 配真实 secret）会得到 `invalid-input-secret`。

## TFV5 侧配置

写入 `res/<port>/config.json`：

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

- 生产环境 `iss` 必须是公网 HTTPS，且与 `AUTH_ISSUER` **完全一致**（含端口、不含末尾斜杠）。
- 多实例部署配 `audience`：平台侧实例的 `audience` 与服务器侧
  `jwt_external_issuers[].audience` 要成对填写。二者都留空时，token 没 `aud`，
  而"不配 `audience` 就不校验"是双方的默认行为
  一个为实例 A 换出的 token
  在实例 B 同样通过验签
- 本地加 `"allow_insecure_http": true`，且地址用 `127.0.0.1` 而不是 `localhost`


## 已知限制

- 客户端 Web 端暂不支持外部登录闭环（浏览器没有 InAppWebView 的 JS 桥），
  只在新标签页打开授权页并提示改用客户端。
- 客户端**不调用**平台的账号接口（`/api/auth/login`、`/api/auth/register`），只走两条路：
  TFV5 账密直登（`/auth/login`）与平台代授权（WebView 打开 `/authorize` → ticket → `/auth/external/login`）。
  站点的人机验证、邮箱验证对客户端没有影响，也**不需要**客户端适配——
  这两步发生在 WebView 加载的平台网页里，已实现。
  只有将来在客户端内做**原生**的平台账号登录/注册界面时，才需要补验证码与验证码输入框。
- 客户端授权页弹层的兜底提示文案为硬编码中文，未走 l10n。
- Turnstile 在 WebView 内的兼容性弱于普通浏览器。
- GitHub 等第三方登录未开始

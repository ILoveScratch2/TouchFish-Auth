TouchFish Auth 可执行版


一、准备

  把 .env.example 复制为 .env，至少填这两项：

    AUTH_BASE_URL   对外可访问的地址（决定 issuer、JWKS 与 OAuth 回调地址）
    AUTH_MASTER_KEY 32 字节随机密钥的 base64

  生成密钥：
    Linux / macOS : python3 -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
    Windows       : py -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"

二、启动

    Linux / macOS : ./touchfish-auth
    Windows       : touchfish-auth.exe

  默认监听 127.0.0.1:8000，可改用环境变量：

    AUTH_HOST=0.0.0.0     对外监听（务必先配好反向代理与 HTTPS）
    AUTH_PORT=8000        端口
    AUTH_LOG_LEVEL=info   debug / info / warning

  然后访问 http://127.0.0.1:8000/login 注册第一个账号。

三、授予管理员

    ./touchfish-auth promote <用户名>
    ./touchfish-auth list                 查看现有用户
    ./touchfish-auth demote <用户名>
    ./touchfish-auth instances            查看已配置的 TouchFish 实例

  管理员只能在本机授予，避免"第一个注册的人自动成为管理员"。

四、随包目录（均相对于本文件）

    .env          运行时配置（需自己创建）
    data/auth.db  数据库（首次启动自动创建）
    keys/         JWT 签名密钥（首次启动自动生成，务必纳入备份）

五、升级

  保留 .env、data/、keys/ 三者，替换其余文件即可。

六、反向代理要点

  - 全站 HTTPS；后端可用 --proxy-headers 等价方式时设 trust proxy，
    或直接配 AUTH_TRUST_PROXY=1（仅当无法用反代提供的机制时）
  - 放行 /authorize、/token、/.well-known/*、/api/*
  - AUTH_COOKIE_SECURE 在 HTTPS 下置 1（默认值即为 1，本地 http 调试才设 0）

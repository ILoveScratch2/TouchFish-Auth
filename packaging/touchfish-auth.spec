# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置
"""
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # spec 放在 packaging/ 下
FRONTEND_DIST = ROOT / "frontend" / "dist"

if not FRONTEND_DIST.is_dir():
    raise SystemExit(
        "未找到 frontend/dist。请先构建前端：cd frontend && npm ci && npm run build"
    )

datas = [
    # 运行期由 settings._RESOURCE_DIR 定位：<_MEIPASS>/frontend/dist
    (str(FRONTEND_DIST), "frontend/dist"),
]

hiddenimports = [
    # uvicorn 这些模块是字符串动态导入的，静态分析扫不到，漏了会在启动时报
    # "Could not import module ..." 或协议实现缺失
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # mailer 里按需构造 MIME 消息
    "email.mime.text",
    "email.mime.multipart",
]

a = Analysis(
    [str(ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(ROOT / "backend")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "unittest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="touchfish-auth",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="touchfish-auth",
)

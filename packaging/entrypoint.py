"""
PyInstaller 打包入口
"""
from __future__ import annotations

import os
import sys

import uvicorn

from app.main import app


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def main() -> None:
    if len(sys.argv) > 1:
        from app.cli import main as cli_main

        raise SystemExit(cli_main(sys.argv[1:]))

    # 默认只监听回环：对外暴露交给反向代理，避免打包版无意中裸奔在公网
    host = os.environ.get("AUTH_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = _int_env("AUTH_PORT", 8000)
    log_level = os.environ.get("AUTH_LOG_LEVEL", "info").strip().lower() or "info"
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()

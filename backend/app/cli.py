"""
TOUCHFISH AUTH CLI TOOL

    python -m app.cli promote alice
    python -m app.cli demote alice
    python -m app.cli list
    python -m app.cli instances
"""
from __future__ import annotations

import argparse
import sys

from .db import Db
from .services import instances as instances_repo
from .services import users as users_service
from .settings import ConfigError, load_settings


def _open():
    try:
        settings = load_settings()
    except ConfigError as exc:
        raise SystemExit(f"配置错误：{exc}") from exc
    return settings, Db(settings.db_path)


def cmd_promote(args: argparse.Namespace) -> int:
    settings, db = _open()
    row = users_service.find_by_login(db, args.username)
    if row is None:
        print(f"找不到用户 {args.username}", file=sys.stderr)
        return 1
    if not users_service.set_role(db, row["id"], "admin"):
        print("更新失败", file=sys.stderr)
        return 1
    db.audit("cli.promote", row["id"], detail=f"by={args.operator}")
    print(f"已授予 {row['username']} 管理员权限（issuer={settings.issuer}）")
    return 0


def cmd_demote(args: argparse.Namespace) -> int:
    _, db = _open()
    row = users_service.find_by_login(db, args.username)
    if row is None:
        print(f"找不到用户 {args.username}", file=sys.stderr)
        return 1
    if users_service.count_admins(db) <= 1 and row["role"] == "admin":
        print("这是最后一个管理员，拒绝降级（否则将无人可管理）", file=sys.stderr)
        return 1
    if not users_service.set_role(db, row["id"], "user"):
        print("更新失败", file=sys.stderr)
        return 1
    db.audit("cli.demote", row["id"], detail=f"by={args.operator}")
    print(f"已取消 {row['username']} 的管理员权限")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    _, db = _open()
    rows = users_service.list_users(db, limit=500)
    if not rows:
        print("（还没有用户）")
        return 0
    print(f"{'用户名':<20} {'角色':<7} {'状态':<11} 创建时间")
    for row in rows:
        import datetime
        created = datetime.datetime.fromtimestamp(row["created_at"]).strftime("%Y-%m-%d %H:%M")
        print(f"{row['username']:<20} {row['role']:<7} {row['status']:<11} {created}")
    print(f"\n共 {len(rows)} 个用户，其中管理员 {users_service.count_admins(db)} 个")
    return 0


def cmd_instances(_: argparse.Namespace) -> int:
    _, db = _open()
    items = instances_repo.list_instances(db)
    if not items:
        print("（还没有实例，请设置 AUTH_DEFAULT_INSTANCE_URL）")
        return 0
    for item in items:
        print(f"{item.id:<10} {item.display_name:<16} {item.base_url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="TouchFish Auth 运维命令")
    parser.add_argument("--operator", default="cli", help="记录进审计日志的操作者标识")
    sub = parser.add_subparsers(dest="command", required=True)

    promote = sub.add_parser("promote", help="授予管理员权限")
    promote.add_argument("username")
    promote.set_defaults(func=cmd_promote)

    demote = sub.add_parser("demote", help="取消管理员权限")
    demote.add_argument("username")
    demote.set_defaults(func=cmd_demote)

    sub.add_parser("list", help="列出用户").set_defaults(func=cmd_list)
    sub.add_parser("instances", help="列出已配置的 TouchFish 实例").set_defaults(func=cmd_instances)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

"""邮件发送。

配置完整时走 SMTP
未配置且开了 AUTH_DEV_MAIL 时把邮件写进内存收件箱
"""
from __future__ import annotations

import smtplib
import time
from email.message import EmailMessage
from typing import Any

DEV_OUTBOX: list[dict[str, Any]] = []
MAX_OUTBOX = 50


def _remember(to: str, subject: str, body: str) -> None:
    DEV_OUTBOX.append({"at": time.time(), "to": to, "subject": subject, "body": body})
    if len(DEV_OUTBOX) > MAX_OUTBOX:
        del DEV_OUTBOX[: len(DEV_OUTBOX) - MAX_OUTBOX]


def send(
    cfg: dict[str, Any],
    to: str,
    subject: str,
    body: str,
    *,
    dev_mail: bool = False,
) -> tuple[bool, str]:
    """返回 (成功, 错误信息)。"""
    host = str(cfg.get("smtp_host") or "").strip()
    sender = str(cfg.get("smtp_from") or "").strip()
    if not host or not sender:
        if dev_mail:
            _remember(to, subject, body)
            return True, ""
        return False, "未配置 SMTP，无法发送邮件"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    port = int(cfg.get("smtp_port") or 465)
    use_tls = bool(cfg.get("smtp_tls", True))
    username = str(cfg.get("smtp_username") or "")
    password = str(cfg.get("smtp_password") or "")

    try:
        if use_tls and port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=12) as smtp:
                if username:
                    smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=12) as smtp:
                if use_tls:
                    smtp.starttls()
                if username:
                    smtp.login(username, password)
                smtp.send_message(message)
    except Exception as exc:  # noqa: BLE001 - 统一转成可展示的错误
        if dev_mail:
            _remember(to, subject, body)
            return True, ""
        return False, f"邮件发送失败：{exc}"

    _remember(to, subject, body)
    return True, ""


def verification_body(site_name: str, code: str, ttl_minutes: int = 15) -> str:
    return (
        f"你正在注册 {site_name}。\n\n"
        f"验证码：{code}\n\n"
        f"{ttl_minutes} 分钟内有效。如果不是你本人操作，请忽略这封邮件。\n"
    )

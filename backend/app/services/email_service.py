"""注册验证码邮件发送服务。"""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings


logger = logging.getLogger(__name__)

_SMTP_TIMEOUT_SECONDS = 15


class EmailDeliveryError(RuntimeError):
    """邮件发送失败，但不向接口层泄漏 SMTP 内部信息。"""


def _validate_code(code: str) -> None:
    """对服务层收到的验证码再次执行安全校验。"""
    if len(code) != 6 or not code.isdigit():
        raise ValueError("验证码必须是 6 位数字")


def _build_message(recipient: str, code: str) -> EmailMessage:
    """构造注册验证码邮件。"""
    message = EmailMessage()
    message["Subject"] = f"{settings.APP_NAME} 注册验证码"
    message["From"] = settings.SMTP_FROM
    message["To"] = recipient

    message.set_content(
        f"你的注册验证码是：{code}\n\n"
        "验证码在 5 分钟内有效，请勿将验证码告诉他人。\n"
        "如果这不是你的操作，请忽略本邮件。"
    )

    return message


def _send_smtp(recipient: str, code: str) -> None:
    """通过 SMTP 同步发送邮件，由异步入口放入工作线程。"""

    message = _build_message(recipient, code)

    with smtplib.SMTP(
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        timeout=_SMTP_TIMEOUT_SECONDS,
    ) as smtp:
        smtp.ehlo()

        if settings.SMTP_USE_TLS:
            # STARTTLS 将后续登录凭据和邮件内容放入加密连接中。
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()

        smtp.login(
            settings.SMTP_USER,
            settings.SMTP_PASSWORD,
        )
        smtp.send_message(message)


async def send_verification_code(
    recipient: str,
    code: str,
) -> None:
    """根据当前环境输出或发送注册验证码。"""

    _validate_code(code)

    if settings.EMAIL_DELIVERY_MODE == "console":
        # 仅供本地开发调试。生产环境不能把验证码写入日志。
        logger.warning(
            "development_verification_code email=%s code=%s",
            recipient,
            code,
        )
        return

    try:
        # smtplib 是同步库，直接调用会阻塞 FastAPI 事件循环。
        await asyncio.to_thread(
            _send_smtp,
            recipient,
            code,
        )
    except Exception as exc:
        # 日志保留异常堆栈供服务端排查，但接口只收到统一异常。
        logger.exception(
            "verification email delivery failed email=%s",
            recipient,
        )
        raise EmailDeliveryError(
            "verification email delivery failed"
        ) from exc

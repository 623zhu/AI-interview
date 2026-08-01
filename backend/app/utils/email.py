"""Email utility: send verification codes via SMTP."""
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings


async def send_verification_code(to_email: str, code: str) -> bool:
    """Send a verification code email. Returns True on success, raises on failure.

    Uses asyncio.to_thread to avoid blocking the event loop during SMTP I/O.
    """

    def _send_sync():
        msg = MIMEMultipart()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email
        msg["Subject"] = "AI Mock Interview — 邮箱验证码"

        body = f"""\
<html>
<body style="font-family: Arial, sans-serif; padding: 20px;">
  <h2 style="color: #667eea;">AI Mock Interview 邮箱验证</h2>
  <p>您的验证码是：</p>
  <div style="font-size: 32px; font-weight: bold; color: #667eea;
              letter-spacing: 8px; padding: 16px 24px; background: #f0f0ff;
              border-radius: 8px; display: inline-block;">
    {code}
  </div>
  <p style="margin-top: 20px; color: #666;">
    验证码 <strong>5 分钟</strong>内有效，请勿泄露给他人。
  </p>
  <hr style="margin-top: 24px; border: none; border-top: 1px solid #eee;">
  <p style="color: #999; font-size: 12px;">
    如果这不是您的操作，请忽略此邮件。
  </p>
</body>
</html>"""

        msg.attach(MIMEText(body, "html", "utf-8"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, to_email, msg.as_string())

        return True

    return await asyncio.to_thread(_send_sync)

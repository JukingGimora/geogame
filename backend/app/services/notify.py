"""待审照片的邮件提醒。

后台不会自己跳出来告诉你有人传了照片,不主动打开就永远不知道。
每小时看一眼:有待审的就发一封,没有就不发——不打扰是这件事能长期开着的前提。
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy import func, select

from app.config import settings
from app.db import async_session_maker
from app.models import Photo

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 3600


def _send(subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = settings.notify_email
    msg.set_content(body)
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as s:
        s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


async def notify_pending_once() -> int:
    """有多少张待审就发一封,返回张数。0 张不发信。"""
    async with async_session_maker() as session:
        pending = await session.scalar(
            select(func.count()).select_from(Photo).where(Photo.status == "pending")
        )
        oldest = await session.scalar(
            select(func.min(Photo.created_at)).where(Photo.status == "pending")
        )
    if not pending:
        return 0
    body = (
        f"有 {pending} 张照片在等审核。\n"
        f"最早的一张提交于 {oldest:%Y-%m-%d %H:%M}(UTC)。\n\n"
        f"{settings.public_base_url}/admin\n"
    )
    await asyncio.to_thread(_send, f"身处雾境:{pending} 张照片待审核", body)
    return pending


async def pending_digest_loop() -> None:
    """跟着服务一起起来,不需要另外配 cron。"""
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.notify_email):
        logger.info("未配置 SMTP,跳过待审提醒")
        return
    while True:
        await asyncio.sleep(INTERVAL_SECONDS)
        try:
            n = await notify_pending_once()
            if n:
                logger.info("已发送待审提醒:%d 张", n)
        except Exception:
            # 发信失败不能把服务带下去,下一个小时再试
            logger.exception("待审提醒发送失败")

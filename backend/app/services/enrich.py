"""照片上线前的 AI 富化:AI 对手的猜测 + 提示②。

放在**上传后**跑而不是审核通过时跑,有两个好处:
  1. 审核页点"通过"不用干等视觉模型(原来要 5 秒),AI 结果早就算好了;
  2. 审核时就能拿 AI 推断的位置跟上传者标注的坐标做比对,这是"疑似标错地点"
     预警的前提——放到通过之后算就太晚了,图都已经上线了。

待审图不会被发到玩家手里(只有 live 状态才进题库),所以提前算不会剧透。
"""
import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.db import async_session_maker
from app.models import AIGuess, Hint, Photo
from app.services.ai_stub import fake_ai_guess, real_ai_guess, real_ai_hint

logger = logging.getLogger(__name__)

HINT2_FALLBACK = "注意画面里的植被与建筑样式(开发桩:正式版由AI生成,审核可改)"


async def enrich_photo(photo_id: int) -> None:
    """给一张照片补齐 AI 猜测和提示②。已经有的不重算,失败不抛(审核时还有兜底)。"""
    try:
        async with async_session_maker() as session:
            photo = await session.get(Photo, photo_id)
            if not photo:
                return
            need_guess = not await session.scalar(select(AIGuess).where(AIGuess.photo_id == photo_id))
            need_hint = not await session.scalar(
                select(Hint).where(Hint.photo_id == photo_id, Hint.level == 2)
            )
            if not (need_guess or need_hint):
                return

            if settings.fake_ai:
                hint2 = None
                guess = await fake_ai_guess(photo) if need_guess else None
            else:
                hint2, guess = await asyncio.gather(
                    real_ai_hint(photo) if need_hint else _none(),
                    real_ai_guess(photo) if need_guess else _none(),
                )

            if need_guess and guess:
                session.add(guess)
            if need_hint:
                session.add(
                    Hint(photo_id=photo_id, level=2, content=hint2 or HINT2_FALLBACK, source="ai")
                )
            await session.commit()
    except Exception:
        # 上传接口已经返回 200 了,这里失败只能记日志;审核通过时会再补一次
        logger.exception("enrich_photo failed for photo %d", photo_id)


async def _none() -> None:
    return None

"""每天三条命。

**命**按人按天算,不按局算——不然死了重开一局就当没事发生,失败就没有代价。
掉光了当天不能再开认真局,除非传一张照片并通过审核,回一条(最多回到三条)。
审核是人工的,可能隔几个小时,所以"传完马上能玩"做不到;这是有意的,
它把"想继续玩"变成"给题库添一张图"。

试过按文化圈解锁(玩到七成才开相邻的),做完拆了:地理是这游戏里最不该设门槛的维度,
而且西欧和拉美还没有照片,巴黎或圣保罗来的人会一个圈都点不开。
进度改成用亮度显示——走得越多越亮,不拦人。按时区认"他从哪个圈出发"也一起删了,
那是为解锁服务的,不解锁就没人用它。
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PointsLedger, Round, Run, User
from app.services.scoring import DECAY_KM, miss_km

DAILY_LIVES = 3
LIFE_BACK = "life_back"  # 照片过审回的那一条命,记在积分流水里


def day_bounds(user: User) -> tuple[datetime, datetime]:
    """这个人"今天"的起止(按他自己的时区),返回的是 UTC 时刻。"""
    offset = timedelta(minutes=user.tz_offset)
    local_now = datetime.now(timezone.utc) + offset
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = (local_start - offset).replace(tzinfo=None)
    return start, start + timedelta(days=1)


async def lives_left(session: AsyncSession, user: User) -> int:
    """今天还剩几条命。"""
    start, end = day_bounds(user)
    # 漫游不掉命,只数认真局
    lost = await session.scalar(
        select(func.count(Round.id))
        .select_from(Round)
        .join(Run, Round.run_id == Run.id)
        .where(
            Run.user_id == user.id,
            Run.mode != "roam",
            Round.finished_at.is_not(None),
            Round.finished_at >= start,
            Round.finished_at < end,
            Round.distance_km > miss_km(func.coalesce(Run.decay_km, DECAY_KM)),
        )
    ) or 0
    back = await session.scalar(
        select(func.count(PointsLedger.id)).where(
            PointsLedger.user_id == user.id,
            PointsLedger.kind == LIFE_BACK,
            PointsLedger.created_at >= start,
            PointsLedger.created_at < end,
        )
    ) or 0
    return max(0, min(DAILY_LIVES, DAILY_LIVES - lost + back))

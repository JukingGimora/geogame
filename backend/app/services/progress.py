"""每天三条命,以及文化圈的解锁。

**命**按人按天算,不按局算——不然死了重开一局就当没事发生,失败就没有代价。
掉光了当天不能再开认真局,除非传一张照片并通过审核,回一条(最多回到三条)。
审核是人工的,可能隔几个小时,所以"传完马上能玩"做不到;这是有意的,
它把"想继续玩"变成"给题库添一张图"。

**解锁**:只能玩已解锁的圈。漫游随机抽到过的圈自动算解锁(新人打完三关手里就有几个),
再往外走要先把手上的圈玩到七成——七成是按该圈**当前上线照片数**实时算的,
达标过就永久算数,不会因为后来又上线了新照片被收回。
"""
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Photo, PointsLedger, Round, Run, User
from app.services.circles import CIRCLE_NEIGHBOURS
from app.services.scoring import DECAY_KM, miss_km

DAILY_LIVES = 3
LIFE_BACK = "life_back"  # 照片过审回的那一条命,记在积分流水里
MASTERED = 0.7           # 玩到这个比例才能往外解锁


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


async def circle_progress(session: AsyncSession, user: User) -> dict[str, tuple[int, int]]:
    """每个圈 →(他玩过几张, 这个圈一共几张上线的)。"""
    total = dict(
        (await session.execute(
            select(Photo.circle, func.count(Photo.id))
            .where(Photo.status == "live", Photo.circle.is_not(None))
            .group_by(Photo.circle)
        )).all()
    )
    played = dict(
        (await session.execute(
            select(Photo.circle, func.count(func.distinct(Photo.id)))
            .select_from(Round)
            .join(Run, Round.run_id == Run.id)
            .join(Photo, Round.photo_id == Photo.id)
            .where(Run.user_id == user.id, Round.finished_at.is_not(None), Photo.circle.is_not(None))
            .group_by(Photo.circle)
        )).all()
    )
    return {c: (played.get(c, 0), n) for c, n in total.items()}


def unlocked_circles(progress: dict[str, tuple[int, int]]) -> set[str]:
    """哪些圈能玩。

    踏进去过的圈直接算解锁(漫游是随机发牌,不受这条规则管);
    玩到七成的圈,把挨着它的圈也打开。一直推到不再有新的为止——
    玩通了东亚就能去东南亚,玩通了东南亚还能再往外,不用每一步都回来重算。
    """
    # 还没有照片的圈不算数:开了也只会得到一句"这里还没有照片"
    playable = {c for c, (_, total) in progress.items() if total}
    open_set = {c for c, (played, _) in progress.items() if played > 0} & playable
    while True:
        grown = set(open_set)
        for circle in open_set:
            played, total = progress[circle]
            if played >= math.ceil(total * MASTERED):
                grown |= set(CIRCLE_NEIGHBOURS.get(circle, ()))
        grown &= playable
        if grown == open_set:
            return open_set
        open_set = grown


def why_locked(circle: str, progress: dict[str, tuple[int, int]], unlocked: set[str]) -> dict | None:
    """这个圈为什么进不去。能进就返回 None。

    挨着的圈里挑进度最靠前的那个来说,玩家才知道该往哪使劲。
    """
    if circle in unlocked:
        return None
    if not progress.get(circle, (0, 0))[1]:
        return {"reason": "circle_empty"}
    if not unlocked:
        # 一个圈都还没踏进去过:说"先解锁挨着的"等于没说,挨着谁?
        return {"reason": "circle_locked_start"}
    gates = [c for c in CIRCLE_NEIGHBOURS.get(circle, ()) if c in unlocked and progress.get(c, (0, 0))[1]]
    if not gates:
        return {"reason": "circle_locked_far"}
    best = max(gates, key=lambda c: progress[c][0] / progress[c][1])
    played, total = progress[best]
    # 向上取整:76 张的七成是 53.2,得玩到 54 张才算过
    need = math.ceil(total * MASTERED) - played
    return {
        "reason": "circle_locked_progress",
        "gate": best,
        "played": played,
        "total": total,
        "need": max(1, need),
    }

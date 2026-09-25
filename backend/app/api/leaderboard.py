from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Photo, Round, Run, User
from app.services import understood
from app.services.auth import get_current_user

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])

TOP_N = 50
BEIJING_OFFSET = timedelta(hours=8)


@router.get("")
async def leaderboard(
    board: str = "best_run",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if board == "points":
        sub = understood.counts_by_uploader()
    elif board == "streak":
        # 连过多少关:比总分有故事——"他连过了 31 关"是能被人记住的数字
        per_run = (
            select(Run.user_id.label("uid"), func.count(Round.id).label("n"))
            .select_from(Round)
            .join(Run, Round.run_id == Run.id)
            .where(Round.finished_at.is_not(None))
            .group_by(Round.run_id, Run.user_id)
            .subquery()
        )
        sub = (
            select(per_run.c.uid.label("uid"), func.max(per_run.c.n).label("v"))
            .group_by(per_run.c.uid)
            .subquery()
        )
    else:
        sub = (
            select(Run.user_id.label("uid"), func.max(Run.total_score).label("v"))
            .where(Run.status == "finished")
            .group_by(Run.user_id)
            .subquery()
        )
    rows = (
        await session.execute(
            select(User.id, User.nickname, User.avatar_url, sub.c.v)
            .join(sub, sub.c.uid == User.id)
            .order_by(sub.c.v.desc(), User.id)
            .limit(TOP_N)
        )
    ).all()
    my_value = await session.scalar(select(sub.c.v).where(sub.c.uid == user.id))
    my_rank = None
    if my_value is not None:
        higher = await session.scalar(select(func.count()).select_from(sub).where(sub.c.v > my_value))
        my_rank = higher + 1
    return {
        "board": board,
        "top": [
            # uid 只用来给前端算头像:昵称默认都叫"旅行者",不带 uid 的话满屏一个样
            {"rank": i + 1, "uid": uid, "nickname": nick, "value": v, "is_me": uid == user.id}
            for i, (uid, nick, avatar_url, v) in enumerate(rows)
        ],
        "me": {"rank": my_rank, "value": my_value, "uid": user.id, "nickname": user.nickname},
        "pulse": await _pulse(session, user),
    }


async def _pulse(session: AsyncSession, user: User) -> dict:
    """社区体温 + 他自己今天的收获。

    榜单只让前几名有感觉,这两行是给所有人的:一行证明这地方是活的,
    一行证明"我被看见了"——不上榜的人也能在这一页找到自己的位置。
    """
    day_start = datetime.combine(
        (datetime.now(timezone.utc) + BEIJING_OFFSET).date(), time.min, tzinfo=timezone.utc
    ) - BEIJING_OFFSET
    return {
        "active_today": await session.scalar(
            select(func.count(func.distinct(Run.user_id)))
            .select_from(Round)
            .join(Run, Round.run_id == Run.id)
            .where(Round.finished_at >= day_start)
        )
        or 0,
        "photos_live": await session.scalar(
            select(func.count()).select_from(Photo).where(Photo.status == "live")
        )
        or 0,
        "photos_today": await session.scalar(
            select(func.count())
            .select_from(Photo)
            .where(Photo.status == "live", Photo.created_at >= day_start)
        )
        or 0,
        "my_seen_today": await session.scalar(understood.seen_since(user.id, day_start)) or 0,
    }

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Run, User
from app.services import understood
from app.services.auth import get_current_user

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])

TOP_N = 50


@router.get("")
async def leaderboard(
    board: str = "best_run",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if board == "points":
        sub = understood.counts_by_uploader()
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
            {"rank": i + 1, "nickname": nick, "avatar_url": avatar_url, "value": v, "is_me": uid == user.id}
            for i, (uid, nick, avatar_url, v) in enumerate(rows)
        ],
        "me": {"rank": my_rank, "value": my_value},
    }

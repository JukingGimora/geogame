"""某个人的公开战绩。

揭晓页看到"这张是谁拍的"、排行榜看到一个名字,点下去总得有东西可看——
否则榜上永远只是一串陌生的名字,这游戏就还是一个人在玩。

只给公开数据:传了多少、被多少人看过、走过哪些地方。不给设备、不给行踪明细。
"""
import functools
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Photo, Round, Run, User
from app.services import understood
from app.services.auth import get_current_user
from app.services.circles import COUNTRIES, LIT_KM
from app.services.cities import nearest_cc

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}")
async def profile(
    user_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "user_not_found")

    photos = await session.scalar(
        select(func.count()).select_from(Photo).where(Photo.uploader_id == user_id, Photo.status == "live")
    )
    seen = (await session.execute(understood.summary_for(user_id))).one()

    rounds_played = await session.scalar(
        select(func.count(Round.id))
        .select_from(Round)
        .join(Run, Round.run_id == Run.id)
        .where(Run.user_id == user_id, Round.finished_at.is_not(None))
    )
    # 最长连关只算认真模式:漫游不掉命,拿来比不公平
    per_run = (
        select(func.count(Round.id).label("n"))
        .select_from(Round)
        .join(Run, Round.run_id == Run.id)
        .where(Round.finished_at.is_not(None), Run.user_id == user_id, Run.mode != "roam")
        .group_by(Round.run_id)
        .subquery()
    )
    best_streak = await session.scalar(select(func.max(per_run.c.n)))

    # 走过的地方:认出来过(LIT_KM 以内)才算,猜得离谱不算去过
    recognized = (
        select(Photo.circle, Photo.country)
        .select_from(Round)
        .join(Run, Round.run_id == Run.id)
        .join(Photo, Round.photo_id == Photo.id)
        .where(Run.user_id == user_id, Round.finished_at.is_not(None), Round.distance_km <= LIT_KM)
    )
    rows = (await session.execute(recognized)).all()

    days = (datetime.now(timezone.utc) - user.created_at.replace(tzinfo=timezone.utc)).days + 1
    return {
        "id": user.id,
        "nickname": user.nickname,
        "joined_days": days,
        "photos": photos or 0,
        "seen": seen.seen or 0,
        "understood": seen.understood or 0,
        "rounds_played": rounds_played or 0,
        "best_streak": best_streak or 0,
        "circles": sorted({c for c, _ in rows if c}),
        # 国家带上国旗:一排国旗比一排国名好认,也不挑语言
        "countries": [
            {"name": name, "flag": _flag(name)} for name in sorted({c for _, c in rows if c})
        ],
    }


@functools.lru_cache(maxsize=1)
def _country_code() -> dict[str, str]:
    """中文国名 → 两位国家代码。按国家中心点就近认,不另维护一张表。"""
    out = {}
    for name, lat, lng, _ in COUNTRIES:
        cc = nearest_cc(lat, lng)
        if cc:
            out[name] = cc
    return out


def _flag(country: str) -> str:
    """两位国家代码 → 国旗 emoji(两个区域指示符拼起来)。认不出来就不给。"""
    cc = _country_code().get(country)
    if not cc or len(cc) != 2:
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in cc.upper())

"""文化圈进度:首页靠它显示九个圈的状态。

点亮的判定是"在那个圈里猜中过 300 公里以内"——不是去过,是认出来过。
这张地图是玩家在这游戏里唯一会一直累积的东西,所以它必须是永久的、看得见的。
"""
from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Photo, Round, Run, User
from app.services.auth import get_current_user
from app.services.circles import CIRCLES, LIT_KM
from app.services.i18n import CIRCLE_DESC_EN, is_en, lang_header
from app.services.progress import lives_left, roam_done

router = APIRouter(prefix="/circles", tags=["circles"])


@router.get("")
async def list_circles(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    lang: str = Depends(lang_header),
):
    live = dict(
        (
            await session.execute(
                select(Photo.circle, func.count())
                .where(Photo.status == "live", Photo.circle.is_not(None))
                .group_by(Photo.circle)
            )
        ).all()
    )
    mine = (
        await session.execute(
            select(
                Photo.circle,
                func.count(func.distinct(Round.photo_id)),
                func.min(Round.distance_km),
                # 认出来过几张:亮度按这个算,走过不等于认出来
                func.count(func.distinct(case((Round.distance_km <= LIT_KM, Round.photo_id)))),
            )
            .select_from(Round)
            .join(Run, Round.run_id == Run.id)
            .join(Photo, Round.photo_id == Photo.id)
            .where(Run.user_id == user.id, Round.finished_at.is_not(None))
            .group_by(Photo.circle)
        )
    ).all()
    played = {c: (n, best, lit) for c, n, best, lit in mine}
    # 我在这个圈里传过几张:点进去只看到"能玩几张"不够,
    # 自己贡献了多少也该看得见——尤其当那个圈里大半是自己传的、因此玩不了的时候
    uploaded = dict(
        (await session.execute(
            select(Photo.circle, func.count())
            .where(Photo.status == "live", Photo.uploader_id == user.id, Photo.circle.is_not(None))
            .group_by(Photo.circle)
        )).all()
    )
    return {
        "lives_left": await lives_left(session, user),
        # 走完新手三关就不再给漫游入口
        "roam_done": await roam_done(session, user),
        "items": [
            {
                # name 一直是中文:它是配色表的键,也是开局时回传的 chapter。
                # 只有 desc 换语言,名字由前端按同一张表翻显示
                "name": name,
                "desc": CIRCLE_DESC_EN.get(name, desc) if is_en(lang) else desc,
                "photos": live.get(name, 0),
                "played": played.get(name, (0, None, 0))[0],
                # 认出来过的张数:地图的亮度按它算,越认得多越亮
                "lit_count": played.get(name, (0, None, 0))[2],
                "lit": (played.get(name, (0, None, 0))[1] or 9e9) <= LIT_KM,
                "mine": uploaded.get(name, 0),
            }
            for name, desc in CIRCLES.items()
        ]
    }

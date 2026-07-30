"""「被理解次数」= 有多少个**不同的人**真的猜过你的照片。

不从 PointsLedger 算:那张表只记了"上传者 +1",没记是谁猜的,无法去重——
同一个人反复玩你的图会被记成多次。改从 rounds→runs 取猜图的人,天然可去重。
"""
from sqlalchemy import func, select

from app.models import Photo, Round, Run

# 只算真的提交了猜测的关(发到手里没猜不算"被理解"),且排除自己玩自己
_CONDITIONS = (Round.finished_at.is_not(None), Run.user_id != Photo.uploader_id)


def counts_by_uploader():
    """子查询:uid -> 猜过他照片的不同人数。给排行榜用。"""
    return (
        select(
            Photo.uploader_id.label("uid"),
            func.count(func.distinct(Run.user_id)).label("v"),
        )
        .select_from(Round)
        .join(Run, Round.run_id == Run.id)
        .join(Photo, Round.photo_id == Photo.id)
        .where(*_CONDITIONS)
        .group_by(Photo.uploader_id)
        .subquery()
    )


def count_for(user_id: int):
    """单个用户的被理解次数。给 /auth/me 用。"""
    return (
        select(func.count(func.distinct(Run.user_id)))
        .select_from(Round)
        .join(Run, Round.run_id == Run.id)
        .join(Photo, Round.photo_id == Photo.id)
        .where(Photo.uploader_id == user_id, *_CONDITIONS)
    )

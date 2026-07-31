"""「被看见」和「被读懂」——上传者这一侧的回报。

不从 PointsLedger 算:那张表只记了"上传者 +1",没记是谁猜的,无法去重——
同一个人反复玩你的图会被记成多次。改从 rounds→runs 取猜图的人,天然可去重。

两个概念要分清:
  被看见 = 有多少不同的人猜过(不论对错)。排行榜用它,因为它跟照片难易无关,
           不会把题库推向"人人都认得的网红地标"。
  被读懂 = 其中猜到 CLOSE_KM 以内的有多少人。只放在个人页,不参与排名。
"""
from sqlalchemy import case, func, select

from app.models import Photo, Round, Run

CLOSE_KM = 100.0  # 判定"读懂"的距离;play.py 发积分用的是同一个标准

# 只算真的提交了猜测的关(发到手里没猜不算),且排除自己玩自己
_CONDITIONS = (Round.finished_at.is_not(None), Run.user_id != Photo.uploader_id)

_SEEN = func.count(func.distinct(Run.user_id))
# distance 超出范围时 case 返回 NULL,COUNT(DISTINCT ...) 会跳过 NULL
_UNDERSTOOD = func.count(func.distinct(case((Round.distance_km <= CLOSE_KM, Run.user_id))))


def counts_by_uploader():
    """子查询:uid -> 看过他照片的不同人数。给排行榜用。

    只统计上传者的话,这个榜上就只有寥寥几个人,而**玩得再多也进不去**——
    线上默认打开的正是这个榜,新玩家看到的就是一块跟自己无关的空地。
    所以把"玩过或传过的人"都收进来,没被看见的记 0,至少人人都能找到自己。
    """
    seen = (
        select(Photo.uploader_id.label("uid"), _SEEN.label("v"))
        .select_from(Round)
        .join(Run, Round.run_id == Run.id)
        .join(Photo, Round.photo_id == Photo.id)
        .where(*_CONDITIONS)
        .group_by(Photo.uploader_id)
        .subquery()
    )
    # 有过完整一轮、或上传过照片的人,都算"参与过"
    participants = (
        select(Run.user_id.label("uid")).where(Run.status == "finished")
        .union(select(Photo.uploader_id.label("uid")))
        .subquery()
    )
    return (
        select(
            participants.c.uid.label("uid"),
            func.coalesce(seen.c.v, 0).label("v"),
        )
        .select_from(participants)
        .join(seen, seen.c.uid == participants.c.uid, isouter=True)
        .subquery()
    )


def summary_for(user_id: int):
    """某人全部照片合计的 (被看见人数, 被读懂人数)。"""
    return (
        select(_SEEN.label("seen"), _UNDERSTOOD.label("understood"))
        .select_from(Round)
        .join(Run, Round.run_id == Run.id)
        .join(Photo, Round.photo_id == Photo.id)
        .where(Photo.uploader_id == user_id, *_CONDITIONS)
    )


def by_photo(photo_ids: list[int]):
    """逐张照片的 (被看见, 被读懂)。给个人页每张下面那行小字用。"""
    return (
        select(Round.photo_id, _SEEN.label("seen"), _UNDERSTOOD.label("understood"))
        .select_from(Round)
        .join(Run, Round.run_id == Run.id)
        .join(Photo, Round.photo_id == Photo.id)
        .where(Round.photo_id.in_(photo_ids), *_CONDITIONS)
        .group_by(Round.photo_id)
    )


def seen_since(user_id: int, since):
    """自 since 之后,有多少不同的人猜过他的照片。给"你走之后又有 N 人看过"用。"""
    return (
        select(_SEEN)
        .select_from(Round)
        .join(Run, Round.run_id == Run.id)
        .join(Photo, Round.photo_id == Photo.id)
        .where(Photo.uploader_id == user_id, Round.finished_at >= since, *_CONDITIONS)
    )

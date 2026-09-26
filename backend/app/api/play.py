from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AIGuess, AuthIdentity, Hint, Photo, PointsLedger, Region, Round, Run, User
from app.services.auth import get_current_user
from app.services.circles import CIRCLES, LIT_KM, locate
from app.services.cities import nearest_city
from app.services.scoring import DECAY_KM, final_score, haversine_km, miss_km, pool_decay_km
from app.services.understood import CLOSE_KM
from app.storage import storage

router = APIRouter(tags=["play"])

LIVES = 3      # 掉光就结束:没有失败就没有"再来一把"
PREFETCH = 2   # 一次多备几关,免得每猜一关都等一次抽题


ROAM_ROUNDS = 3  # 漫游固定三关:5 关的完成率只有 28%,3 关是 38%,而且短局才有"打完了"这回事


class RunIn(BaseModel):
    region_id: int | None = None
    # roam = 新人和随便玩玩的人:不掉命、三关结束、不上连关榜
    mode: str = "serious"
    # 文化圈名,或 china/world:决定这一局从哪个池子抽题,但所有人排同一个榜
    chapter: str | None = None
    # 从"叫朋友猜这张"的分享进来时带上,这一局就从那张开始
    photo_id: int | None = None


class GuessIn(BaseModel):
    lat: float
    lng: float


class HintIn(BaseModel):
    level: int


@router.post("/runs")
async def create_run(body: RunIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    unfinished = await session.scalar(
        select(Run).where(Run.user_id == user.id, Run.status == "playing").order_by(Run.id.desc())
    )
    if unfinished:
        # 手上有没打完的局时,如果是从"叫朋友猜这张"进来的,不能直接把旧局还回去——
        # 那样分享指定的照片永远轮不到,点链接的人只会觉得"点了没反应"。
        # 把那张换进下一个还没猜的关,承诺兑现,进度也不丢。
        if body.photo_id:
            await _swap_in_photo(session, unfinished, body.photo_id, user)
        return await run_state(unfinished.id, user, session)

    q = _playable(user, body.chapter)
    if body.region_id:
        region = await session.get(Region, body.region_id)
        if not region:
            raise HTTPException(404, "region_not_found")
        sub = select(Region.id).where(Region.path.like(f"{region.path}%"))
        q = q.where(Photo.region_id.in_(sub))

    playable = q
    played_ids = await _played_photo_ids(session, user)
    photos = list(
        await session.scalars(
            playable.where(Photo.id.notin_(played_ids))
            .order_by(func.random())
            .limit(ROAM_ROUNDS if body.mode == "roam" else PREFETCH)
        )
    )

    # 朋友指名要你猜的那张,排到第一关。
    # 拿不到就默默按普通一局走——他是被朋友叫来的,不能因为"这张你玩过了"就把人挡在门外。
    if body.photo_id:
        wanted = await session.get(Photo, body.photo_id)
        if (
            wanted
            and wanted.status == "live"
            and wanted.uploader_id != user.id
            and wanted.id not in played_ids
        ):
            photos = [wanted] + [p for p in photos if p.id != wanted.id][: PREFETCH - 1]

    if not photos:
        # 三种空库的原因,前端提示各不相同
        if await session.scalar(select(func.count()).select_from(playable.subquery())):
            detail = "all_photos_played"
        elif await session.scalar(select(func.count()).select_from(q.subquery())):
            detail = "only_own_photos"  # 库里只剩自己传的图,种子期很常见
        else:
            detail = "no_photos_available"
        raise HTTPException(409, detail)
    # 尺子按这一局的题池算一次就定下来:期间有新照片上线也不改写进行中的局。
    # 取两列遍历一遍是 O(n),现在两百张几十微秒,十万张也就十几毫秒,而且一局只算一次。
    coords = (await session.execute(playable.with_only_columns(Photo.lat, Photo.lng))).all()
    mode = "roam" if body.mode == "roam" else "serious"
    run = Run(
        user_id=user.id,
        region_id=body.region_id,
        mode=mode,
        decay_km=pool_decay_km([(lat, lng) for lat, lng in coords]),
    )
    session.add(run)
    await session.flush()
    for i, p in enumerate(photos):
        session.add(Round(run_id=run.id, photo_id=p.id, order_index=i))
    await session.commit()
    return await run_state(run.id, user, session)


def _playable(user: User, chapter: str | None):
    """能发给这个人的题:已上线、不是他自己传的(知道答案等于白送满分)、限定文化圈。

    chapter 可以是文化圈名(东亚/西欧/…),也可以是 china/world 这种粗分。
    """
    q = select(Photo).where(Photo.status == "live", Photo.uploader_id != user.id)
    if chapter in CIRCLES:
        q = q.where(Photo.circle == chapter)
    elif chapter == "china":
        q = q.where(Photo.country == "中国")
    elif chapter == "world":
        q = q.where(Photo.country != "中国")
    return q


async def _played_photo_ids(session: AsyncSession, user: User) -> list[int]:
    """猜过的不再出现——知道答案的关既没意思,也会把纪录刷成假的。"""
    return list(
        await session.scalars(
            select(Round.photo_id).join(Run, Round.run_id == Run.id).where(Run.user_id == user.id)
        )
    )


async def _lives_used(session: AsyncSession, run: Run) -> int:
    """失手次数由关卡记录现算,不存字段,省一次线上迁移。"""
    return await session.scalar(
        select(func.count(Round.id)).where(
            Round.run_id == run.id,
            Round.distance_km > miss_km(run.decay_km or DECAY_KM),
            Round.finished_at.is_not(None),
        )
    ) or 0


async def _append_round(session: AsyncSession, run: Run, user: User) -> bool:
    """再接一关。题库被他打空就返回 False,由调用方结束这一局。"""
    played = await _played_photo_ids(session, user)
    photo = await session.scalar(
        _playable(user, None).where(Photo.id.notin_(played)).order_by(func.random()).limit(1)
    )
    if not photo:
        return False
    last = await session.scalar(select(func.max(Round.order_index)).where(Round.run_id == run.id))
    session.add(Round(run_id=run.id, photo_id=photo.id, order_index=(last or 0) + 1))
    return True


async def _swap_in_photo(session: AsyncSession, run: Run, photo_id: int, user: User) -> None:
    """把指定照片换进这一局下一个未完成的关卡。换不了就什么都不做。"""
    photo = await session.get(Photo, photo_id)
    if not photo or photo.status != "live" or photo.uploader_id == user.id:
        return
    already = (
        await session.scalars(
            select(Round.photo_id).join(Run, Round.run_id == Run.id).where(Run.user_id == user.id)
        )
    ).all()
    if photo_id in already:
        return  # 他已经见过这张了,换了也没意义
    nxt = await session.scalar(
        select(Round)
        .where(Round.run_id == run.id, Round.finished_at.is_(None))
        .order_by(Round.order_index)
    )
    if nxt:
        nxt.photo_id = photo_id
        await session.commit()


@router.get("/runs/{run_id}")
async def run_state(run_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    run = await session.get(Run, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(404, "run_not_found")
    rounds = (
        await session.scalars(select(Round).where(Round.run_id == run.id).order_by(Round.order_index))
    ).all()
    out = []
    for r in rounds:
        photo = await session.get(Photo, r.photo_id)
        item = {
            "round_id": r.id,
            "order": r.order_index,
            "photo_url": storage.url(photo.file_key),
            "story_teaser": photo.story[:30] + "…" if len(photo.story) > 30 else photo.story,
            "finished": r.finished_at is not None,
            "hints_mask": r.hints_mask,
        }
        if r.finished_at is not None:
            item.update({"score": r.score, "distance_km": r.distance_km})
        out.append(item)
    finished_rounds = sum(1 for r in rounds if r.finished_at is not None)
    rank = None
    if run.status == "finished" and run.mode != "roam" and finished_rounds:
        per_run = (
            select(Run.user_id.label("uid"), func.count(Round.id).label("n"))
            .select_from(Round)
            .join(Run, Round.run_id == Run.id)
            .where(Round.finished_at.is_not(None), Run.mode != "roam")
            .group_by(Round.run_id, Run.user_id)
            .subquery()
        )
        best = select(per_run.c.uid, func.max(per_run.c.n).label("v")).group_by(per_run.c.uid).subquery()
        rank = (await session.scalar(select(func.count()).select_from(best).where(best.c.v > finished_rounds)) or 0) + 1
    return {
        "run_id": run.id,
        "status": run.status,
        "total_score": run.total_score,
        "mode": run.mode,
        "lives_left": LIVES if run.mode == "roam" else max(0, LIVES - await _lives_used(session, run)),
        "streak": finished_rounds,
        "total_rounds": ROAM_ROUNDS if run.mode == "roam" else None,
        "rank": rank,
        "rounds": out,
    }


async def _get_open_round(session: AsyncSession, round_id: int, user: User) -> tuple[Round, Run]:
    rnd = await session.get(Round, round_id)
    if not rnd:
        raise HTTPException(404, "round_not_found")
    run = await session.get(Run, rnd.run_id)
    if run.user_id != user.id:
        raise HTTPException(404, "round_not_found")
    if rnd.finished_at is not None:
        raise HTTPException(409, "round_already_finished")
    return rnd, run


@router.post("/rounds/{round_id}/hints")
async def unlock_hint(
    round_id: int, body: HintIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    if body.level not in (1, 2, 3, 4):
        raise HTTPException(422, "invalid_hint_level")
    rnd, _ = await _get_open_round(session, round_id, user)
    hint = await session.scalar(
        select(Hint).where(Hint.photo_id == rnd.photo_id, Hint.level == body.level)
    )
    if not hint:
        raise HTTPException(404, "hint_not_available")
    rnd.hints_mask |= 1 << (body.level - 1)
    await session.commit()
    return {"level": body.level, "content": hint.content, "hints_mask": rnd.hints_mask}


@router.post("/rounds/{round_id}/guess")
async def submit_guess(
    round_id: int, body: GuessIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    rnd, run = await _get_open_round(session, round_id, user)
    photo = await session.get(Photo, rnd.photo_id)
    distance = haversine_km(photo.lat, photo.lng, body.lat, body.lng)
    score = final_score(distance, rnd.hints_mask, run.decay_km or DECAY_KM)
    rnd.guess_lat, rnd.guess_lng = body.lat, body.lng
    rnd.distance_km = round(distance, 2)
    rnd.score = score
    rnd.finished_at = datetime.now(timezone.utc)
    run.total_score += score

    # 漫游走满三关就收,不掉命;认真模式是三条命掉光或题库走空
    roam = run.mode == "roam"
    lives_left = LIVES if roam else LIVES - await _lives_used(session, run)
    ended = None
    if roam:
        finished_rounds = await session.scalar(
            select(func.count(Round.id)).where(Round.run_id == run.id, Round.finished_at.is_not(None))
        )
        if finished_rounds >= ROAM_ROUNDS:
            ended = "roam_done"
    elif lives_left <= 0:
        ended = "lives"
    if not ended and not roam:
        pending = await session.scalar(
            select(func.count(Round.id)).where(Round.run_id == run.id, Round.finished_at.is_(None))
        )
        if pending < PREFETCH and not await _append_round(session, run, user):
            if pending == 0:
                ended = "pool_empty"
    if ended:
        run.status = "finished"
    streak = await session.scalar(
        select(func.count(Round.id)).where(Round.run_id == run.id, Round.finished_at.is_not(None))
    )

    # 这一关点亮了哪个圈:猜进 LIT_KM 才算"认出来过"。
    # 之前只在地图上默默变色,猜完那一刻什么都不说,最该被看见的一步反而没人看见。
    lit_now = False
    if distance <= LIT_KM and photo.circle:
        earlier = await session.scalar(
            select(func.count(Round.id))
            .select_from(Round)
            .join(Run, Round.run_id == Run.id)
            .join(Photo, Round.photo_id == Photo.id)
            .where(
                Run.user_id == user.id,
                Photo.circle == photo.circle,
                Round.distance_km <= LIT_KM,
                Round.finished_at.is_not(None),
                Round.id != rnd.id,
            )
        )
        lit_now = not earlier

    # 差几百公里但国家猜对了,在全球题库里已经算认出来了,该说一句
    guess_country, _ = locate(body.lat, body.lng)
    await _award_uploader(session, photo, user, distance)

    ai = await session.scalar(select(AIGuess).where(AIGuess.photo_id == photo.id))
    uploader = await session.get(User, photo.uploader_id)
    await session.commit()
    return {
        "distance_km": rnd.distance_km,
        "score": score,
        "mode": run.mode,
        "lives_left": max(0, lives_left),
        "streak": streak,
        "ended": ended,
        "truth": {"lat": photo.lat, "lng": photo.lng},
        "circle": photo.circle,
        "circle_lit": lit_now,
        "country": photo.country,
        "country_match": bool(photo.country) and guess_country == photo.country,
        # 猜完才给:知道"离 Tbilisi 3 公里"比只看见一个点有意思得多
        "place": _place_label(photo),
        "story": photo.story,
        "uploader": {"id": uploader.id, "nickname": uploader.nickname},
        "ai": None
        if not ai
        else {
            "lat": ai.lat,
            "lng": ai.lng,
            "distance_km": ai.distance_km,
            "score": ai.score,
            "reasoning": ai.reasoning,
            "beaten": score > ai.score,
        },
        "run_status": run.status,
        "run_total_score": run.total_score,
    }


def _place_label(photo: Photo) -> str | None:
    hit = nearest_city(photo.lat, photo.lng)
    if not hit:
        return photo.country
    name, km = hit
    return f"{name} 附近" if km <= 15 else f"{name} 以外 {km:.0f}km"


async def _award_uploader(session: AsyncSession, photo: Photo, guesser: User, distance_km: float) -> None:
    if photo.uploader_id == guesser.id:
        return
    guesser_devices = (
        await session.scalars(
            select(AuthIdentity.provider_uid).where(
                AuthIdentity.user_id == guesser.id, AuthIdentity.provider == "guest"
            )
        )
    ).all()
    uploader_devices = (
        await session.scalars(
            select(AuthIdentity.provider_uid).where(
                AuthIdentity.user_id == photo.uploader_id, AuthIdentity.provider == "guest"
            )
        )
    ).all()
    if set(guesser_devices) & set(uploader_devices):
        return
    session.add(
        PointsLedger(user_id=photo.uploader_id, delta=1, kind="photo_played", ref_type="photo", ref_id=photo.id)
    )
    if distance_km <= CLOSE_KM:
        session.add(
            PointsLedger(
                user_id=photo.uploader_id, delta=1, kind="photo_guessed_close", ref_type="photo", ref_id=photo.id
            )
        )

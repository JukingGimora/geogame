from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AIGuess, AuthIdentity, Hint, Photo, PointsLedger, Region, Round, Run, User
from app.services.auth import get_current_user
from app.services.circles import CIRCLES, LIT_KM, locate
from app.services.progress import DAILY_LIVES, lives_left
from app.services.scoring import DECAY_KM, final_score, haversine_km, pool_decay_km
from app.services.understood import CLOSE_KM
from app.storage import storage

router = APIRouter(tags=["play"])

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

    serious = body.mode != "roam"
    if serious:
        # 命按天算,不按局算:死了重开一局就当没事发生的话,失败没有代价
        if await lives_left(session, user) <= 0:
            raise HTTPException(409, "no_lives")

    q = _playable(user, body.chapter)
    if body.region_id:
        region = await session.get(Region, body.region_id)
        if not region:
            raise HTTPException(404, "region_not_found")
        sub = select(Region.id).where(Region.path.like(f"{region.path}%"))
        q = q.where(Photo.region_id.in_(sub))

    playable = q
    played_ids = await _played_photo_ids(session, user)
    want = ROAM_ROUNDS if body.mode == "roam" else PREFETCH
    # 多抓一些再筛:随机拿到的那几张可能全挤在一个地方
    candidates = list(
        await session.scalars(
            playable.where(Photo.id.notin_(played_ids)).order_by(func.random()).limit(want * 8)
        )
    )
    photos = _spread(candidates, [], want)

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
        # 三种空库的原因,前端提示各不相同。
        # 原来这两个分支查的是同一个 q,"库里只剩自己传的图"那条永远走不到——
        # 一个人把题库填满之后,他看到的是"你都玩过了",208 张摆在那儿却没人告诉他为什么。
        others = await session.scalar(select(func.count()).select_from(playable.subquery()))
        anyones = await session.scalar(
            select(func.count()).select_from(_playable(user, body.chapter, include_own=True).subquery())
        )
        if others:
            detail = "all_photos_played"
        elif anyones:
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
        chapter=body.chapter,
        decay_km=pool_decay_km([(lat, lng) for lat, lng in coords]),
    )
    session.add(run)
    await session.flush()
    for i, p in enumerate(photos):
        session.add(Round(run_id=run.id, photo_id=p.id, order_index=i))
    await session.commit()
    return await run_state(run.id, user, session)


# 同一局里不出两张挨着的照片。20 张斐济照片里有 18 张挤在楠迪:
# 认出第一张之后,后面每一张都是白送的满分,连关纪录也就成了假的。
# 0.15 度在赤道上约 16 公里,往高纬度只会更严,宁严勿松。
NEAR_DEG = 0.15


def _spread(candidates: list[Photo], used: list[tuple[float, float]], want: int) -> list[Photo]:
    """从候选里挑互相不挨着的。挑不够就拿挨着的补——题池小的圈不能因为这条规则提前收摊。"""
    taken = list(used)
    picked: list[Photo] = []
    spare: list[Photo] = []
    for p in candidates:
        if len(picked) == want:
            break
        if any(abs(p.lat - la) < NEAR_DEG and abs(p.lng - ln) < NEAR_DEG for la, ln in taken):
            spare.append(p)
            continue
        picked.append(p)
        taken.append((p.lat, p.lng))
    return (picked + spare)[:want]


def _playable(user: User, chapter: str | None, include_own: bool = False):
    """能发给这个人的题:已上线、不是他自己传的(知道答案等于白送满分)、限定文化圈。

    chapter 可以是文化圈名(东亚/西欧/…),也可以是 china/world 这种粗分。
    include_own 只在开不出局、要判断"到底为什么"时用:
    题库里除了他自己的没别的图,和他把别人的都玩过了,是两回事,提示也不一样。
    """
    q = select(Photo).where(Photo.status == "live")
    if not include_own:
        q = q.where(Photo.uploader_id != user.id)
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


async def _append_round(session: AsyncSession, run: Run, user: User) -> bool:
    """再接一关。题库被他打空就返回 False,由调用方结束这一局。"""
    played = await _played_photo_ids(session, user)
    candidates = list(
        await session.scalars(
            _playable(user, run.chapter).where(Photo.id.notin_(played)).order_by(func.random()).limit(40)
        )
    )
    used = (
        await session.execute(
            select(Photo.lat, Photo.lng)
            .join(Round, Round.photo_id == Photo.id)
            .where(Round.run_id == run.id)
        )
    ).all()
    picked = _spread(candidates, [(la, ln) for la, ln in used], 1)
    if not picked:
        return False
    photo = picked[0]
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
        # 只列这张图真有的提示:没故事就没①,AI 给不出通名就没④,
        # 列出来点不开比不列更糟
        have = sorted(await session.scalars(select(Hint.level).where(Hint.photo_id == photo.id)))
        item = {
            "round_id": r.id,
            "order": r.order_index,
            "photo_url": storage.url(photo.file_key),
            "story_teaser": photo.story[:30] + "…" if len(photo.story) > 30 else photo.story,
            "finished": r.finished_at is not None,
            "hints_mask": r.hints_mask,
            # 这一关真正能买的提示
            "hint_levels": have,
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
        "lives_left": DAILY_LIVES if run.mode == "roam" else await lives_left(session, user),
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
    # 先把这一关落库再数命:剩几条是去数据库 COUNT 的,不 flush 的话当前这关还在内存里,
    # 数不到。掉第三条命的那一关因此被漏掉,玩家多打了一关才结束。
    await session.flush()

    # 漫游走满三关就收,不掉命;认真模式是三条命掉光或题库走空
    roam = run.mode == "roam"
    left = DAILY_LIVES if roam else await lives_left(session, user)
    ended = None
    if roam:
        finished_rounds = await session.scalar(
            select(func.count(Round.id)).where(Round.run_id == run.id, Round.finished_at.is_not(None))
        )
        if finished_rounds >= ROAM_ROUNDS:
            ended = "roam_done"
    elif left <= 0:
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
        "lives_left": max(0, left),
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


def _place_label(photo: Photo) -> str:
    """揭晓时报拍摄点的坐标,不再反查最近的城市。

    反查会挑出人口五百的村子,名字玩家没听过,有时离拍摄点还挺远——报得越具体越像报错。
    而揭晓页的地图本来就标着城市名,地名那件事它做得更准。坐标是原始事实,永远不会错。
    """
    ns = "N" if photo.lat >= 0 else "S"
    ew = "E" if photo.lng >= 0 else "W"
    return f"{abs(photo.lat):.4f}°{ns}, {abs(photo.lng):.4f}°{ew}"


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

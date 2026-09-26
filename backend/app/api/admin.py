import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import case
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import (
    AIGuess,
    AuthIdentity,
    Comment,
    Event,
    Feedback,
    Hint,
    Photo,
    PointsLedger,
    Region,
    Report,
    Round,
    Run,
    User,
)
from app.services.auth import require_admin
from app.services.circles import coarse_area, locate
from app.services.cities import nearest_city
from app.services.enrich import enrich_photo
from app.services.geo import nearest_province, resolve_city
from app.storage import process_image, storage

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

logger = logging.getLogger(__name__)

BEIJING_OFFSET = timedelta(hours=8)


class RejectIn(BaseModel):
    reason: str


class StoryIn(BaseModel):
    story: str


@router.get("/photos")
async def pending_photos(
    status: str = "pending",
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    limit = max(1, min(limit, 100))
    total = await session.scalar(select(func.count()).select_from(Photo).where(Photo.status == status))
    photos = (
        await session.scalars(
            select(Photo).where(Photo.status == status).order_by(Photo.id).limit(limit).offset(offset)
        )
    ).all()
    result = []
    for p in photos:
        region_name = None
        if p.region_id:
            province = await session.get(Region, p.region_id)
            if province:
                macro = await session.get(Region, province.parent_id) if province.parent_id else None
                city = await resolve_city(province.name, p.lat, p.lng)
                parts = [n for n in (macro.name if macro else None, province.name, city) if n]
                region_name = "·".join(parts)

        # AI 一共给三样东西,审核页要能一次看全:
        #   猜前的线索(玩家花分数买的)、猜后的结论、以及它推断的位置。
        clue = await session.scalar(
            select(Hint.content).where(Hint.photo_id == p.id, Hint.level == 2)
        )
        # AI 推测的位置,用来对照上传者标注的坐标——标错地点的图肉眼很难发现,
        # 但"AI说陕西、他标海南"这种矛盾一眼就能看出来。
        ai = await session.scalar(select(AIGuess).where(AIGuess.photo_id == p.id))
        ai_out = None
        if ai:
            ai_out = {
                "lat": ai.lat,
                "lng": ai.lng,
                "distance_km": ai.distance_km,
                "region_name": await _describe_point(session, ai.lat, ai.lng),
                # 它自己说的地方。跟上面那个对不上,就是小地名查不到、落点退到了国家中心
                "place": ai.place,
                "reasoning": ai.reasoning,
            }

        result.append(
            {
                "id": p.id,
                "url": storage.url(p.file_key),
                "lat": p.lat,
                "lng": p.lng,
                "region_name": region_name,
                "country": p.country,
                # 跟玩家看到的提示④一致,方便你核对"这条提示给得合不合适"
                "area": coarse_area(p.country, p.lat, p.lng) if p.country else None,
                # 审核要靠它判断坐标标没标对:"俄罗斯·北部"看不出来,"离 Suzdal 2 公里"一眼就知道
                "city": _city_label(p.lat, p.lng),
                "circle": p.circle,
                "story": p.story,
                "uploader_id": p.uploader_id,
                "created_at": p.created_at.isoformat(),
                "clue": clue,
                "ai": ai_out,
            }
        )
    return {"items": result, "total": total, "limit": limit, "offset": offset}


@router.post("/photos/{photo_id}/approve")
async def approve_photo(photo_id: int, session: AsyncSession = Depends(get_session)):
    photo = await session.get(Photo, photo_id)
    if not photo or photo.status != "pending":
        raise HTTPException(404, "photo_not_pending")
    photo.status = "live"
    # AI 猜测和提示②在上传时就已经算好了(services/enrich.py),这里只补纯程序生成的提示①③④。
    # 万一当时后台任务失败,兜底再跑一次,不让图带着空 AI 上线。
    await enrich_photo(photo.id)
    await _generate_system_hints(session, photo)
    await session.commit()
    return {"id": photo.id, "status": photo.status}


@router.post("/photos/enrich-missing")
async def enrich_missing(limit: int = 20, session: AsyncSession = Depends(get_session)):
    """给缺 AI 数据的待审图补算。

    上传时自动富化只覆盖新图,这个接口用来消化改动之前的积压队列,
    以及后台任务偶发失败留下的漏网之鱼——否则那些图只能在点"通过"时现算,又要干等。
    """
    limit = max(1, min(limit, 100))
    has_guess = select(AIGuess.photo_id)
    has_hint2 = select(Hint.photo_id).where(Hint.level == 2)
    ids = (
        await session.scalars(
            select(Photo.id)
            .where(Photo.status == "pending")
            .where(Photo.id.notin_(has_guess) | Photo.id.notin_(has_hint2))
            .order_by(Photo.id)
            .limit(limit)
        )
    ).all()

    sem = asyncio.Semaphore(3)  # 别把 AI 接口打满

    async def one(pid: int) -> None:
        async with sem:
            await enrich_photo(pid)

    await asyncio.gather(*(one(i) for i in ids))
    remaining = await session.scalar(
        select(func.count())
        .select_from(Photo)
        .where(Photo.status == "pending")
        .where(Photo.id.notin_(has_guess) | Photo.id.notin_(has_hint2))
    )
    return {"enriched": len(ids), "remaining": remaining}


@router.post("/photos/import")
async def import_photo(
    file: UploadFile = File(...),
    lat: float = Form(...),
    lng: float = Form(...),
    story: str = Form(""),
    uploader_id: int = Form(...),
    session: AsyncSession = Depends(get_session),
):
    """从电脑上批量导入自己的照片。

    手机端那个上传接口一次一张、还有每天 20 张的配额,几百张存量根本传不完。
    这条只给管理员用:坐标由脚本从 EXIF 里读出来,不用一张张在地图上点。
    """
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(422, "invalid_coordinates")
    uploader = await session.get(User, uploader_id)
    if not uploader:
        raise HTTPException(404, "uploader_not_found")
    data = await file.read()
    try:
        image = process_image(data)
    except Exception:
        raise HTTPException(422, "invalid_image")
    digest = hashlib.sha256(image).hexdigest()
    dup = await session.scalar(
        select(Photo.id).where(Photo.file_hash == digest, Photo.status.in_(("pending", "live")))
    )
    if dup:
        return {"id": dup, "duplicate": True}
    try:
        file_key = storage.save(image)
    except Exception:
        logger.exception("storage.save failed during import (%d bytes)", len(image))
        raise HTTPException(503, "storage_unavailable")
    country, circle = locate(lat, lng)
    province = await nearest_province(session, lat, lng) if country.startswith("中国") else None
    photo = Photo(
        uploader_id=uploader_id,
        file_key=file_key,
        lat=lat,
        lng=lng,
        region_id=province.id if province else None,
        country=country,
        circle=circle,
        story=story[:2000],
        file_hash=digest,
    )
    session.add(photo)
    await session.commit()
    return {"id": photo.id, "status": photo.status, "country": country, "circle": circle}


@router.post("/photos/{photo_id}/story")
async def edit_story(photo_id: int, body: StoryIn, session: AsyncSession = Depends(get_session)):
    """补写或改写故事。

    批量导入的照片没有故事,而故事是这个游戏最值钱的部分——审核时必须能补。
    已上线的照片也能改,顺手把提示①(故事前半句)一起更新。
    """
    photo = await session.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404, "photo_not_found")
    photo.story = body.story[:2000]
    await session.execute(sa_delete(Hint).where(Hint.photo_id == photo_id, Hint.level == 1))
    if photo.story:
        session.add(Hint(photo_id=photo_id, level=1, content=story_teaser(photo.story), source="uploader"))
    await session.commit()
    return {"id": photo.id, "story": photo.story}


@router.post("/photos/backfill-circles")
async def backfill_circles(limit: int = 500, session: AsyncSession = Depends(get_session)):
    """给还没有文化圈的老照片补上。加字段那次迁移之后跑一遍即可。"""
    photos = (
        await session.scalars(select(Photo).where(Photo.circle.is_(None)).limit(limit))
    ).all()
    for p in photos:
        p.country, p.circle = locate(p.lat, p.lng)
    await session.commit()
    return {"updated": len(photos)}


@router.post("/photos/backfill-hashes")
async def backfill_hashes(limit: int = 200, session: AsyncSession = Depends(get_session)):
    """给改动之前上传的照片补 file_hash,否则重复上传检测对老图形同虚设。

    存储里的文件已经是 process_image 的输出,所以直接哈希存储字节就等于上传时算的值。
    """
    limit = max(1, min(limit, 500))
    photos = (
        await session.scalars(
            select(Photo).where(Photo.file_hash.is_(None)).order_by(Photo.id).limit(limit)
        )
    ).all()
    done, failed = 0, 0
    for p in photos:
        try:
            p.file_hash = hashlib.sha256(storage.read(p.file_key)).hexdigest()
            done += 1
        except Exception:
            logger.warning("cannot hash photo %d (file_key=%s)", p.id, p.file_key)
            failed += 1
    await session.commit()
    remaining = await session.scalar(
        select(func.count()).select_from(Photo).where(Photo.file_hash.is_(None))
    )
    return {"hashed": done, "failed": failed, "remaining": remaining}


@router.delete("/photos/{photo_id}")
async def delete_photo(photo_id: int, session: AsyncSession = Depends(get_session)):
    photo = await session.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404, "photo_not_found")
    await session.execute(sa_delete(Hint).where(Hint.photo_id == photo_id))
    await session.execute(sa_delete(AIGuess).where(AIGuess.photo_id == photo_id))
    storage.delete(photo.file_key)
    await session.delete(photo)
    await session.commit()
    return {"id": photo_id, "deleted": True}


@router.get("/feedback")
async def list_feedback(status: str = "open", session: AsyncSession = Depends(get_session)):
    rows = (
        await session.scalars(select(Feedback).where(Feedback.status == status).order_by(Feedback.id.desc()))
    ).all()
    return [
        {
            "id": f.id,
            "user_id": f.user_id,
            "content": f.content,
            "contact": f.contact,
            "created_at": f.created_at.isoformat(),
        }
        for f in rows
    ]


@router.post("/feedback/{feedback_id}/close")
async def close_feedback(feedback_id: int, session: AsyncSession = Depends(get_session)):
    fb = await session.get(Feedback, feedback_id)
    if not fb:
        raise HTTPException(404, "feedback_not_found")
    fb.status = "closed"
    await session.commit()
    return {"id": fb.id, "status": fb.status}


PROBE_KEY_PREFIX = "smoke-"


@router.post("/probe-cleanup")
async def probe_cleanup(session: AsyncSession = Depends(get_session)):
    """删掉冒烟脚本账号留下的一切。

    冒烟脚本每次都真的打一关,不清的话它会上排行榜,还会把上传者的"被看见"
    和"今日活跃"各多算一个人。只认 smoke- 开头的游客设备号,碰不到真实用户。
    """
    uids = (
        await session.scalars(
            select(AuthIdentity.user_id).where(
                AuthIdentity.provider == "guest", AuthIdentity.provider_uid.startswith(PROBE_KEY_PREFIX)
            )
        )
    ).all()
    if not uids:
        return {"users": 0}
    runs = select(Run.id).where(Run.user_id.in_(uids))
    await session.execute(sa_delete(Round).where(Round.run_id.in_(runs)))
    for model in (Run, Event, Feedback, PointsLedger, Comment, Report, AuthIdentity):
        await session.execute(sa_delete(model).where(model.user_id.in_(uids)))
    await session.execute(sa_delete(User).where(User.id.in_(uids)))
    await session.commit()
    return {"users": len(uids)}


@router.post("/photos/{photo_id}/reject")
async def reject_photo(photo_id: int, body: RejectIn, session: AsyncSession = Depends(get_session)):
    photo = await session.get(Photo, photo_id)
    if not photo or photo.status != "pending":
        raise HTTPException(404, "photo_not_pending")
    photo.status = "rejected"
    photo.reject_reason = body.reason[:255]
    await session.commit()
    return {"id": photo.id, "status": photo.status}


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)):
    """三道证伪门里能靠数据算的两条:次日留存、分享率。见 docs/立项报告.md 第八节。"""
    users = (await session.scalars(select(User))).all()
    now_bj_date = (datetime.now(timezone.utc) + BEIJING_OFFSET).date()

    eligible, retained = 0, 0
    for u in users:
        cohort_date = (u.created_at + BEIJING_OFFSET).date()
        next_date = cohort_date + timedelta(days=1)
        if now_bj_date <= next_date:
            continue  # 次日还没完整过完,不计入分母
        eligible += 1
        window_start = datetime.combine(next_date, datetime.min.time(), tzinfo=timezone.utc) - BEIJING_OFFSET
        window_end = window_start + timedelta(days=1)
        hit = await session.scalar(
            select(func.count())
            .select_from(Event)
            .where(Event.user_id == u.id, Event.created_at >= window_start, Event.created_at < window_end)
        )
        if hit:
            retained += 1

    recap_viewers = await session.scalar(
        select(func.count(func.distinct(Event.user_id))).where(Event.event_type == "round_recap_view")
    )
    sharers = await session.scalar(
        select(func.count(func.distinct(Event.user_id))).where(Event.event_type == "share_click")
    )
    profile_hint_viewers = await session.scalar(
        select(func.count(func.distinct(Event.user_id))).where(Event.event_type == "profile_hint_view")
    )
    profile_hint_clickers = await session.scalar(
        select(func.count(func.distinct(Event.user_id))).where(Event.event_type == "profile_hint_click")
    )
    total_events = await session.scalar(select(func.count()).select_from(Event))

    # AI 对手的强度是否合适:赢太多玩家挫败,输太多"赢了AI"就不值钱了。
    # 数据本来就都在,只是没算过。
    duel = (
        await session.execute(
            select(
                func.count().label("rounds"),
                func.sum(case((Round.score > AIGuess.score, 1), else_=0)).label("player_wins"),
                func.avg(Round.distance_km).label("avg_player_km"),
                func.avg(AIGuess.distance_km).label("avg_ai_km"),
            )
            .select_from(Round)
            .join(AIGuess, AIGuess.photo_id == Round.photo_id)
            .where(Round.finished_at.is_not(None))
        )
    ).one()

    return {
        "total_users": len(users),
        "d1_retention": {
            "eligible": eligible,
            "retained": retained,
            "rate": round(retained / eligible, 4) if eligible else None,
        },
        # 分母曾经用 recap_viewers(看过关卡结算的人),但后来地图页、排行榜也能分享了,
        # 分子里混进了没玩过的人,算出过 2.57 这种大于 1 的"比率"。改成占全部用户的比例。
        "share_rate": {
            "users": len(users),
            "sharers": sharers or 0,
            "rate": round((sharers or 0) / len(users), 4) if users else None,
            "recap_viewers": recap_viewers or 0,
        },
        "profile_hint_rate": {
            "viewers": profile_hint_viewers or 0,
            "clickers": profile_hint_clickers or 0,
            "rate": round((profile_hint_clickers or 0) / profile_hint_viewers, 4) if profile_hint_viewers else None,
        },
        "cohorts": await _cohorts(session),
        "ai_duel": {
            "rounds": duel.rounds or 0,
            "player_wins": duel.player_wins or 0,
            "ai_win_rate": round(1 - (duel.player_wins or 0) / duel.rounds, 4) if duel.rounds else None,
            "avg_player_km": round(duel.avg_player_km, 1) if duel.avg_player_km is not None else None,
            "avg_ai_km": round(duel.avg_ai_km, 1) if duel.avg_ai_km is not None else None,
        },
        "total_events": total_events,
    }


NEW_USER_DAYS = 7


async def _cohorts(session: AsyncSession) -> dict:
    """新老用户各自的上传率、通关率。

    立项报告第三道门原本写的是"非熟人上传",但熟人这个界线没法严格界定。
    换成按注册时间分组问同一件事:**后来的人**——没有人情压力的那批——
    是不是也会传照片、也会把一轮打完。老用户那栏是参照系。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=NEW_USER_DAYS)
    out = {}
    for name, cond in (("new", User.created_at >= cutoff), ("old", User.created_at < cutoff)):
        total = await session.scalar(select(func.count()).select_from(User).where(cond))
        uploaders = await session.scalar(
            select(func.count(func.distinct(Photo.uploader_id)))
            .select_from(Photo)
            .join(User, User.id == Photo.uploader_id)
            .where(cond)
        )
        finishers = await session.scalar(
            select(func.count(func.distinct(Run.user_id)))
            .select_from(Run)
            .join(User, User.id == Run.user_id)
            .where(Run.status == "finished", cond)
        )
        out[name] = {
            "users": total or 0,
            "uploaders": uploaders or 0,
            "upload_rate": round((uploaders or 0) / total, 4) if total else None,
            "finishers": finishers or 0,
            "finish_rate": round((finishers or 0) / total, 4) if total else None,
        }
    return out


def _city_label(lat: float, lng: float) -> str | None:
    hit = nearest_city(lat, lng)
    return f"{hit[0]} 附近 {hit[1]}km" if hit else None


async def _describe_point(session: AsyncSession, lat: float, lng: float) -> str | None:
    """任意坐标 → 人话描述,给审核页并排对照用。

    以前一律走中国省份表:AI 猜在撒马尔罕,这里却显示"新疆·喀什"——
    AI 是对的,标签把它冤枉了。境外的点要按国家和最近的城市说。
    """
    country, _ = locate(lat, lng)
    if country.startswith("中国"):
        province = await nearest_province(session, lat, lng)
        if not province:
            return country
        macro = await session.get(Region, province.parent_id) if province.parent_id else None
        city = await resolve_city(province.name, lat, lng)
        return "·".join(n for n in (macro.name if macro else None, province.name, city) if n)
    hit = nearest_city(lat, lng)
    return f"{country}·{hit[0]}" if hit else country


async def _generate_system_hints(session: AsyncSession, photo: Photo) -> None:
    """提示①(故事)与③(国家)——纯程序生成,不经AI(幻觉隔离)。

    提示②(AI线索)和④(关键字)不在这里:它们是网络请求,上传时由 services/enrich.py 算好入库。

    故事整段给,不再砍半:实测 208 个故事里 187 个压根没提地名,8% 提的是别处的地名
    (「这里俄罗斯客人特别多」拍的是中国),砍掉反而帮倒忙;真说漏的只有 5 个,审核时改一个字比写一套过滤划算。
    """
    # 重新通过一张图(改过故事、之前被驳回过)会再走一遍这里,
    # 旧的先删掉——不然撞上 (photo_id, level) 的唯一索引,整个「通过」按钮 500
    await session.execute(sa_delete(Hint).where(Hint.photo_id == photo.id, Hint.level.in_((1, 3, 4))))
    if photo.story:
        session.add(Hint(photo_id=photo.id, level=1, content=photo.story[:255], source="uploader"))
    if not photo.circle:
        photo.country, photo.circle = locate(photo.lat, photo.lng)
    # 文化圈那一级去掉了:从地图选圈进来的人,等于花钱买自己刚点过的东西。
    # 剩下两级都从真实坐标算,不经 AI:国家 → 国家的哪一角。
    session.add(Hint(photo_id=photo.id, level=3, content=f"在{photo.country}", source="system"))
    session.add(
        Hint(
            photo_id=photo.id,
            level=4,
            content=f"在{coarse_area(photo.country, photo.lat, photo.lng)}",
            source="system",
        )
    )

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AIGuess, Event, Feedback, Hint, Photo, Region, Round, User
from app.services.auth import require_admin
from app.services.enrich import enrich_photo
from app.services.geo import nearest_province, resolve_city
from app.storage import storage

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

BEIJING_OFFSET = timedelta(hours=8)


class RejectIn(BaseModel):
    reason: str


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
                "reasoning": ai.reasoning,
            }

        result.append(
            {
                "id": p.id,
                "url": storage.url(p.file_key),
                "lat": p.lat,
                "lng": p.lng,
                "region_name": region_name,
                "story": p.story,
                "uploader_id": p.uploader_id,
                "created_at": p.created_at.isoformat(),
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
        "share_rate": {
            "recap_viewers": recap_viewers or 0,
            "sharers": sharers or 0,
            "rate": round((sharers or 0) / recap_viewers, 4) if recap_viewers else None,
        },
        "profile_hint_rate": {
            "viewers": profile_hint_viewers or 0,
            "clickers": profile_hint_clickers or 0,
            "rate": round((profile_hint_clickers or 0) / profile_hint_viewers, 4) if profile_hint_viewers else None,
        },
        "ai_duel": {
            "rounds": duel.rounds or 0,
            "player_wins": duel.player_wins or 0,
            "ai_win_rate": round(1 - (duel.player_wins or 0) / duel.rounds, 4) if duel.rounds else None,
            "avg_player_km": round(duel.avg_player_km, 1) if duel.avg_player_km is not None else None,
            "avg_ai_km": round(duel.avg_ai_km, 1) if duel.avg_ai_km is not None else None,
        },
        "total_events": total_events,
    }


async def _describe_point(session: AsyncSession, lat: float, lng: float) -> str | None:
    """任意坐标 → 「大区·省·市」,给审核页并排对照用。"""
    province = await nearest_province(session, lat, lng)
    if not province:
        return None
    macro = await session.get(Region, province.parent_id) if province.parent_id else None
    city = await resolve_city(province.name, lat, lng)
    return "·".join(n for n in (macro.name if macro else None, province.name, city) if n)


async def _generate_system_hints(session: AsyncSession, photo: Photo) -> None:
    """提示①(故事前半句)与③④(大区/省份)——纯程序生成,不经AI(幻觉隔离)。

    提示②(AI线索)不在这里:它是网络请求,上传时就由 services/enrich.py 算好入库了。
    """
    if photo.story:
        teaser = photo.story[: max(6, len(photo.story) // 2)]
        session.add(Hint(photo_id=photo.id, level=1, content=teaser + "…", source="uploader"))
    if photo.region_id:
        province = await session.get(Region, photo.region_id)
        if province:
            macro = await session.get(Region, province.parent_id) if province.parent_id else None
            if macro:
                session.add(Hint(photo_id=photo.id, level=3, content=f"在{macro.name}地区", source="system"))
            session.add(Hint(photo_id=photo.id, level=4, content=f"在{province.name}", source="system"))

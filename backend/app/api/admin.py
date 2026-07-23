from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import Event, Feedback, Hint, Photo, Region, User
from app.services.ai_stub import fake_ai_guess, real_ai_guess
from app.services.auth import require_admin
from app.storage import storage

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

BEIJING_OFFSET = timedelta(hours=8)


class RejectIn(BaseModel):
    reason: str


@router.get("/photos")
async def pending_photos(status: str = "pending", session: AsyncSession = Depends(get_session)):
    photos = (
        await session.scalars(select(Photo).where(Photo.status == status).order_by(Photo.id))
    ).all()
    return [
        {
            "id": p.id,
            "url": storage.url(p.file_key),
            "lat": p.lat,
            "lng": p.lng,
            "story": p.story,
            "uploader_id": p.uploader_id,
            "created_at": p.created_at.isoformat(),
        }
        for p in photos
    ]


@router.post("/photos/{photo_id}/approve")
async def approve_photo(photo_id: int, session: AsyncSession = Depends(get_session)):
    photo = await session.get(Photo, photo_id)
    if not photo or photo.status != "pending":
        raise HTTPException(404, "photo_not_pending")
    photo.status = "live"
    await _generate_system_hints(session, photo)
    if settings.fake_ai:
        await fake_ai_guess(session, photo)
    else:
        await real_ai_guess(session, photo)
    await session.commit()
    return {"id": photo.id, "status": photo.status}


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
    total_events = await session.scalar(select(func.count()).select_from(Event))

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
        "total_events": total_events,
    }


async def _generate_system_hints(session: AsyncSession, photo: Photo) -> None:
    """提示①(故事前半句)与③④(大区/省份)——纯程序生成,不经AI(幻觉隔离)。"""
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
    session.add(
        Hint(photo_id=photo.id, level=2, content="注意画面里的植被与建筑样式(开发桩:正式版由AI生成,审核可改)", source="ai")
    )

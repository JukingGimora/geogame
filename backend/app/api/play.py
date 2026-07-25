from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AIGuess, AuthIdentity, Hint, Photo, PointsLedger, Region, Round, Run, User
from app.services.auth import get_current_user
from app.services.scoring import final_score, haversine_km
from app.storage import storage

router = APIRouter(tags=["play"])

ROUNDS_PER_RUN = 5
CLOSE_KM = 100.0


class RunIn(BaseModel):
    region_id: int | None = None


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
        return await run_state(unfinished.id, user, session)

    q = select(Photo).where(Photo.status == "live")
    if body.region_id:
        region = await session.get(Region, body.region_id)
        if not region:
            raise HTTPException(404, "region_not_found")
        sub = select(Region.id).where(Region.path.like(f"{region.path}%"))
        q = q.where(Photo.region_id.in_(sub))

    played_ids = (
        await session.scalars(select(Round.photo_id).join(Run, Round.run_id == Run.id).where(Run.user_id == user.id))
    ).all()
    photos = (
        await session.scalars(q.where(Photo.id.notin_(played_ids)).order_by(func.random()).limit(ROUNDS_PER_RUN))
    ).all()
    if not photos:
        # 区分"库里真没图"和"库里有图但这个用户全玩过了",前端提示不一样
        total_live = await session.scalar(select(func.count()).select_from(q.subquery()))
        raise HTTPException(409, "all_photos_played" if total_live else "no_photos_available")
    run = Run(user_id=user.id, region_id=body.region_id)
    session.add(run)
    await session.flush()
    for i, p in enumerate(photos):
        session.add(Round(run_id=run.id, photo_id=p.id, order_index=i))
    await session.commit()
    return await run_state(run.id, user, session)


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
    return {"run_id": run.id, "status": run.status, "total_score": run.total_score, "rounds": out}


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
    score = final_score(distance, rnd.hints_mask)
    rnd.guess_lat, rnd.guess_lng = body.lat, body.lng
    rnd.distance_km = round(distance, 2)
    rnd.score = score
    rnd.finished_at = datetime.now(timezone.utc)
    run.total_score += score

    unfinished = await session.scalar(
        select(func.count(Round.id)).where(Round.run_id == run.id, Round.finished_at.is_(None))
    )
    if unfinished == 0:
        run.status = "finished"

    await _award_uploader(session, photo, user, distance)

    ai = await session.scalar(select(AIGuess).where(AIGuess.photo_id == photo.id))
    uploader = await session.get(User, photo.uploader_id)
    await session.commit()
    return {
        "distance_km": rnd.distance_km,
        "score": score,
        "truth": {"lat": photo.lat, "lng": photo.lng},
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

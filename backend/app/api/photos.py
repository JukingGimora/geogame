import hashlib
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AIGuess, Hint, Photo, Round, User
from app.services.auth import get_current_user
from app.services.geo import nearest_province
from app.storage import process_image, storage

router = APIRouter(prefix="/photos", tags=["photos"])
logger = logging.getLogger(__name__)


@router.post("")
async def upload_photo(
    file: UploadFile = File(...),
    lat: float = Form(...),
    lng: float = Form(...),
    story: str = Form(""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(422, "invalid_coordinates")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "file_too_large")
    try:
        image = process_image(data)
    except Exception:
        logger.warning("cannot decode upload (%d bytes, content_type=%s)", len(data), file.content_type)
        raise HTTPException(422, "invalid_image")
    # 只跟 pending/live 比:被拒或已删的图不占用这张照片,别人还应该能传
    digest = hashlib.sha256(image).hexdigest()
    dup = await session.scalar(
        select(Photo.id).where(Photo.file_hash == digest, Photo.status.in_(("pending", "live")))
    )
    if dup:
        raise HTTPException(409, "duplicate_photo")

    try:
        file_key = storage.save(image)
    except Exception:
        # 存储挂了不能报成"图片有问题":用户会一直换图,而换哪张都不可能成功
        logger.exception("storage.save failed (%d bytes)", len(image))
        raise HTTPException(503, "storage_unavailable")
    province = await nearest_province(session, lat, lng)
    photo = Photo(
        uploader_id=user.id,
        file_key=file_key,
        lat=lat,
        lng=lng,
        region_id=province.id if province else None,
        story=story[:2000],
        file_hash=digest,
    )
    session.add(photo)
    await session.commit()
    # 这里**不**触发 AI 推理:上传是开放的,谁都能一次推几十张,自动跑等于让垃圾图也烧 API 费。
    # 改由审核页的「补算AI」按钮批量触发(POST /admin/photos/enrich-missing),先筛一眼再花钱。
    return {"id": photo.id, "status": photo.status}


@router.delete("/{photo_id}")
async def delete_my_photo(
    photo_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    photo = await session.get(Photo, photo_id)
    if not photo or photo.uploader_id != user.id:
        raise HTTPException(404, "photo_not_found")
    played = await session.scalar(select(func.count()).select_from(Round).where(Round.photo_id == photo_id))
    if played:
        # 删了会让引用它的 rounds 变成孤儿,连带把别人的历史成绩和自己的被理解次数搞坏
        raise HTTPException(409, "photo_already_played")
    await session.execute(sa_delete(Hint).where(Hint.photo_id == photo_id))
    await session.execute(sa_delete(AIGuess).where(AIGuess.photo_id == photo_id))
    storage.delete(photo.file_key)
    await session.delete(photo)
    await session.commit()
    return {"id": photo_id, "deleted": True}


@router.get("/mine")
async def my_photos(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    photos = (
        await session.scalars(
            select(Photo).where(Photo.uploader_id == user.id).order_by(Photo.id.desc())
        )
    ).all()
    return [
        {
            "id": p.id,
            "url": storage.url(p.file_key),
            "status": p.status,
            "reject_reason": p.reject_reason,
            "story": p.story,
            "created_at": p.created_at.isoformat(),
        }
        for p in photos
    ]

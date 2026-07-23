from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Photo, User
from app.services.auth import get_current_user
from app.services.geo import nearest_province
from app.storage import storage

router = APIRouter(prefix="/photos", tags=["photos"])


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
        file_key = storage.save_image(data)
    except Exception:
        raise HTTPException(422, "invalid_image")
    province = await nearest_province(session, lat, lng)
    photo = Photo(
        uploader_id=user.id,
        file_key=file_key,
        lat=lat,
        lng=lng,
        region_id=province.id if province else None,
        story=story[:2000],
    )
    session.add(photo)
    await session.commit()
    return {"id": photo.id, "status": photo.status}


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

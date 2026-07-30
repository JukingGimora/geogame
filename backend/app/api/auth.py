import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import PointsLedger, User
from app.services.auth import get_current_user, guest_login, wechat_login
from app.storage import process_image, storage

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


class GuestIn(BaseModel):
    device_key: str = Field(min_length=8, max_length=128)
    nickname: str | None = None
    avatar_url: str | None = None


class WechatIn(BaseModel):
    code: str = Field(min_length=1, max_length=128)


class ProfileIn(BaseModel):
    nickname: str | None = None
    avatar_url: str | None = None


@router.post("/guest")
async def login_guest(body: GuestIn, session: AsyncSession = Depends(get_session)):
    user, token = await guest_login(session, body.device_key, body.nickname, body.avatar_url)
    return {"token": token, "user": {"id": user.id, "nickname": user.nickname, "avatar_url": user.avatar_url}}


@router.post("/wechat")
async def login_wechat(
    body: WechatIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    target_user, token = await wechat_login(session, user, body.code)
    return {
        "token": token,
        "user": {"id": target_user.id, "nickname": target_user.nickname, "avatar_url": target_user.avatar_url},
    }


@router.post("/avatar")
async def upload_avatar(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "file_too_large")
    try:
        image = process_image(data)
    except Exception:
        logger.warning("cannot decode avatar (%d bytes)", len(data))
        raise HTTPException(422, "invalid_image")
    try:
        file_key = storage.save(image)
    except Exception:
        logger.exception("storage.save failed for avatar (%d bytes)", len(image))
        raise HTTPException(503, "storage_unavailable")
    return {"url": storage.url(file_key)}


@router.post("/profile")
async def update_profile(body: ProfileIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if body.nickname is not None:
        user.nickname = body.nickname
    if body.avatar_url is not None:
        user.avatar_url = body.avatar_url
    await session.commit()
    return {"id": user.id, "nickname": user.nickname, "avatar_url": user.avatar_url}


@router.get("/me")
async def me(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    points = await session.scalar(
        select(func.coalesce(func.sum(PointsLedger.delta), 0)).where(PointsLedger.user_id == user.id)
    )
    return {"id": user.id, "nickname": user.nickname, "avatar_url": user.avatar_url, "points": points}

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
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
    Report,
    Round,
    Run,
    User,
)
from app.models import Round as RoundModel
from app.models import Run as RunModel
from app.services import understood
from app.services.auth import get_current_user, guest_login, wechat_login
from app.services.avatar import clean_avatar_url
from app.services.names import is_default
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
    # 静默丢弃而不是报错:本地存着个临时路径不该导致登不上
    avatar = clean_avatar_url(body.avatar_url)
    user, token = await guest_login(session, body.device_key, body.nickname, avatar)
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
        cleaned = clean_avatar_url(body.avatar_url)
        if cleaned is None:
            raise HTTPException(422, "invalid_avatar_url")
        user.avatar_url = cleaned
    await session.commit()
    return {"id": user.id, "nickname": user.nickname, "avatar_url": user.avatar_url}


@router.get("/me")
async def me(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    # 跟排行榜口径一致:算"多少个不同的人猜过我的照片",不是积分流水求和
    row = (await session.execute(understood.summary_for(user.id))).one()
    # 开场页据此决定去哪:没玩过的直接丢进第一关,玩过的落到世界地图
    played = await session.scalar(
        select(func.count(RoundModel.id))
        .select_from(RoundModel)
        .join(RunModel, RoundModel.run_id == RunModel.id)
        .where(RunModel.user_id == user.id, RoundModel.finished_at.is_not(None))
    )
    return {
        "id": user.id,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
        "points": row.seen or 0,
        # 还没自己起过名字的人,才提示他去设置
        "default_name": is_default(user.id, user.nickname),
        "rounds_played": played or 0,
    }


@router.delete("/account")
async def delete_account(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """注销:把这个人的一切抹掉,不可恢复。

    平台规则要求用户能自己删掉全部数据,不只是一张张删照片——昵称、设备标识、
    微信 openid、玩过的记录都算。他上传的照片也是他的数据,一起删,
    连带删掉别人猜这些照片留下的关卡记录(否则那些记录会指向一张不存在的图)。
    别人的总分记在 runs 上,不受影响,排行榜不会乱。
    """
    photo_ids = (await session.scalars(select(Photo.id).where(Photo.uploader_id == user.id))).all()
    file_keys = (await session.scalars(select(Photo.file_key).where(Photo.uploader_id == user.id))).all()
    if photo_ids:
        for model in (Hint, AIGuess):
            await session.execute(sa_delete(model).where(model.photo_id.in_(photo_ids)))
        await session.execute(sa_delete(Round).where(Round.photo_id.in_(photo_ids)))
        await session.execute(sa_delete(Comment).where(Comment.photo_id.in_(photo_ids)))
        await session.execute(sa_delete(Report).where(Report.photo_id.in_(photo_ids)))
        await session.execute(sa_delete(Photo).where(Photo.id.in_(photo_ids)))

    await session.execute(sa_delete(Round).where(Round.run_id.in_(select(Run.id).where(Run.user_id == user.id))))
    for model in (Run, Event, Feedback, PointsLedger, Comment, Report, AuthIdentity):
        await session.execute(sa_delete(model).where(model.user_id == user.id))
    await session.execute(sa_delete(User).where(User.id == user.id))
    await session.commit()

    # 图片文件放在最后删:数据库提交成功了才动存储,否则删一半会留下引用不到的图
    for key in file_keys:
        try:
            storage.delete(key)
        except Exception:
            logger.warning("storage.delete failed for %s (账号已注销,文件残留)", key)
    return {"deleted": True}

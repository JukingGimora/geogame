from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import AuthIdentity, User
from app.services.names import default_nickname


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def _find_guest(session: AsyncSession, device_key: str) -> AuthIdentity | None:
    return await session.scalar(
        select(AuthIdentity).where(AuthIdentity.provider == "guest", AuthIdentity.provider_uid == device_key)
    )


async def guest_login(
    session: AsyncSession,
    device_key: str,
    nickname: str | None = None,
    avatar_url: str | None = None,
) -> tuple[User, str]:
    identity = await _find_guest(session, device_key)
    if identity:
        user = await session.get(User, identity.user_id)
        if nickname and user.nickname != nickname:
            user.nickname = nickname
        if avatar_url and user.avatar_url != avatar_url:
            user.avatar_url = avatar_url
        await session.commit()
    else:
        user = User(nickname=nickname, avatar_url=avatar_url)
        session.add(user)
        await session.flush()
        # 名字要等 id 出来才能算:同一个 id 永远是同一个名字
        if not user.nickname:
            user.nickname = default_nickname(user.id)
        session.add(AuthIdentity(user_id=user.id, provider="guest", provider_uid=device_key))
        try:
            await session.commit()
        except IntegrityError:
            # 小程序启动时会并发打好几个请求,同一台设备的两次登录都以为自己是新人,
            # 撞上唯一索引就 500——用户一进来就是崩的。让后到的那个认领先建好的账号。
            await session.rollback()
            identity = await _find_guest(session, device_key)
            if not identity:
                raise
            user = await session.get(User, identity.user_id)
    return user, create_token(user.id)


async def _wechat_code2session(code: str) -> str | None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={
                "appid": settings.wechat_appid,
                "secret": settings.wechat_secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
    data = resp.json()
    return data.get("openid")


async def wechat_login(session: AsyncSession, current_user: User, code: str) -> tuple[User, str]:
    """把微信身份挂到当前(游客)用户上;如果这个openid之前已经绑过别的用户,则切换登录到那个已有账号。"""
    openid = await _wechat_code2session(code)
    if not openid:
        raise HTTPException(400, "wechat_code_invalid")
    identity = await session.scalar(
        select(AuthIdentity).where(AuthIdentity.provider == "wechat", AuthIdentity.provider_uid == openid)
    )
    if identity:
        user = await session.get(User, identity.user_id)
    else:
        session.add(AuthIdentity(user_id=current_user.id, provider="wechat", provider_uid=openid))
        user = current_user
    await session.commit()
    return user, create_token(user.id)


async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "missing_token")
    try:
        payload = jwt.decode(auth[7:], settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid_token")
    user = await session.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "user_not_found")
    return user


async def require_admin(request: Request) -> None:
    if request.headers.get("X-Admin-Token") != settings.admin_token:
        raise HTTPException(403, "admin_only")

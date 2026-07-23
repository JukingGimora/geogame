from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Event, User
from app.services.auth import get_current_user

router = APIRouter(prefix="/events", tags=["events"])


class EventIn(BaseModel):
    event_type: str = Field(min_length=1, max_length=32)
    ref_type: str = ""
    ref_id: int | None = None
    meta: str = Field(default="", max_length=500)


@router.post("")
async def log_event(
    body: EventIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    session.add(
        Event(
            user_id=user.id,
            event_type=body.event_type,
            ref_type=body.ref_type,
            ref_id=body.ref_id,
            meta=body.meta,
        )
    )
    await session.commit()
    return {"ok": True}

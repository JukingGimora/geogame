from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Feedback, User
from app.services.auth import get_current_user

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackIn(BaseModel):
    content: str = Field(min_length=2, max_length=1000)
    contact: str | None = Field(default=None, max_length=128)


@router.post("")
async def submit_feedback(
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    fb = Feedback(user_id=user.id, content=body.content, contact=body.contact)
    session.add(fb)
    await session.commit()
    return {"id": fb.id}

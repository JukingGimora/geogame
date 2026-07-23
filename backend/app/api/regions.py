from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Photo, Region

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("")
async def list_regions(level: str = "province", session: AsyncSession = Depends(get_session)):
    regions = (await session.scalars(select(Region).where(Region.level == level).order_by(Region.id))).all()
    counts = dict(
        (
            await session.execute(
                select(Photo.region_id, func.count(Photo.id))
                .where(Photo.status == "live")
                .group_by(Photo.region_id)
            )
        ).all()
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "level": r.level,
            "parent_id": r.parent_id,
            "lat": r.lat,
            "lng": r.lng,
            "live_photos": counts.get(r.id, 0),
        }
        for r in regions
    ]

import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/geo", tags=["geo"])

GEODATA_DIR = Path(__file__).resolve().parents[2] / "geodata"
DATAV_URL = "https://geo.datav.aliyun.com/areas_v3/bound/{code}.json"


@router.get("/{adcode}")
async def boundary(adcode: str):
    """行政区边界 GeoJSON。数据自托管于 geodata/,缺失时从公开数据集下载一次并永久缓存。"""
    if not re.fullmatch(r"\d{6}", adcode):
        raise HTTPException(422, "invalid_adcode")
    GEODATA_DIR.mkdir(exist_ok=True)
    path = GEODATA_DIR / f"{adcode}.json"
    if not path.exists():
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(DATAV_URL.format(code=f"{adcode}_full"))
            if r.status_code != 200:
                r = await client.get(DATAV_URL.format(code=adcode))
            if r.status_code != 200:
                raise HTTPException(404, "boundary_not_found")
            path.write_bytes(r.content)
    return FileResponse(path, media_type="application/json", headers={"Cache-Control": "public, max-age=86400"})

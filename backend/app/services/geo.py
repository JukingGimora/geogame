"""区域树种子与归属。V0 用省级质心最近邻做归属(开发桩);上线前换逆地理编码 Provider。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Region
from app.services.scoring import haversine_km

MACRO_OF = {
    "北京": "华北", "天津": "华北", "河北": "华北", "山西": "华北", "内蒙古": "华北",
    "辽宁": "东北", "吉林": "东北", "黑龙江": "东北",
    "上海": "华东", "江苏": "华东", "浙江": "华东", "安徽": "华东", "福建": "华东", "江西": "华东", "山东": "华东", "台湾": "华东",
    "河南": "华中", "湖北": "华中", "湖南": "华中",
    "广东": "华南", "广西": "华南", "海南": "华南", "香港": "华南", "澳门": "华南",
    "重庆": "西南", "四川": "西南", "贵州": "西南", "云南": "西南", "西藏": "西南",
    "陕西": "西北", "甘肃": "西北", "青海": "西北", "宁夏": "西北", "新疆": "西北",
}

PROVINCES = [
    ("北京", 39.90, 116.40), ("天津", 39.13, 117.20), ("河北", 38.04, 114.51), ("山西", 37.87, 112.55),
    ("内蒙古", 40.82, 111.66), ("辽宁", 41.80, 123.43), ("吉林", 43.90, 125.33), ("黑龙江", 45.80, 126.53),
    ("上海", 31.23, 121.47), ("江苏", 32.06, 118.80), ("浙江", 30.27, 120.15), ("安徽", 31.86, 117.28),
    ("福建", 26.08, 119.30), ("江西", 28.68, 115.86), ("山东", 36.67, 117.02), ("河南", 34.75, 113.62),
    ("湖北", 30.59, 114.31), ("湖南", 28.23, 112.94), ("广东", 23.13, 113.26), ("广西", 22.82, 108.32),
    ("海南", 20.02, 110.35), ("重庆", 29.56, 106.55), ("四川", 30.65, 104.08), ("贵州", 26.65, 106.63),
    ("云南", 25.04, 102.71), ("西藏", 29.65, 91.14), ("陕西", 34.34, 108.94), ("甘肃", 36.06, 103.83),
    ("青海", 36.62, 101.78), ("宁夏", 38.47, 106.26), ("新疆", 43.79, 87.63), ("台湾", 25.03, 121.56),
    ("香港", 22.32, 114.17), ("澳门", 22.19, 113.54),
]

MACRO_CENTERS = {
    "华北": (40.0, 114.0), "东北": (44.0, 125.0), "华东": (30.5, 118.5), "华中": (31.0, 113.5),
    "华南": (22.5, 111.5), "西南": (28.5, 102.5), "西北": (38.5, 100.0),
}


async def seed_regions(session: AsyncSession) -> None:
    existing = await session.scalar(select(Region.id).limit(1))
    if existing:
        return
    china = Region(level="country", name="中国", name_en="China", lat=35.0, lng=104.0, path="")
    session.add(china)
    await session.flush()
    china.path = f"/{china.id}"
    macros: dict[str, Region] = {}
    for name, (lat, lng) in MACRO_CENTERS.items():
        r = Region(parent_id=china.id, level="macro", name=name, lat=lat, lng=lng)
        session.add(r)
        macros[name] = r
    await session.flush()
    for r in macros.values():
        r.path = f"{china.path}/{r.id}"
    for name, lat, lng in PROVINCES:
        macro = macros[MACRO_OF[name]]
        p = Region(parent_id=macro.id, level="province", name=name, lat=lat, lng=lng)
        session.add(p)
        await session.flush()
        p.path = f"{macro.path}/{p.id}"
    await session.commit()


async def nearest_province(session: AsyncSession, lat: float, lng: float) -> Region | None:
    provinces = (await session.scalars(select(Region).where(Region.level == "province"))).all()
    if not provinces:
        return None
    return min(provinces, key=lambda r: haversine_km(lat, lng, r.lat, r.lng))


async def macro_of_province(session: AsyncSession, province: Region) -> Region | None:
    if province.parent_id is None:
        return None
    return await session.get(Region, province.parent_id)

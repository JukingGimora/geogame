"""区域树种子与归属。V0 用省级质心最近邻做归属(开发桩);上线前换逆地理编码 Provider。"""
import json
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Region
from app.services.scoring import haversine_km

GEODATA_DIR = Path(__file__).resolve().parents[2] / "geodata"
DATAV_URL = "https://geo.datav.aliyun.com/areas_v3/bound/{code}.json"

PROVINCE_ADCODE = {
    "北京": 110000, "天津": 120000, "河北": 130000, "山西": 140000, "内蒙古": 150000,
    "辽宁": 210000, "吉林": 220000, "黑龙江": 230000, "上海": 310000, "江苏": 320000,
    "浙江": 330000, "安徽": 340000, "福建": 350000, "江西": 360000, "山东": 370000,
    "河南": 410000, "湖北": 420000, "湖南": 430000, "广东": 440000, "广西": 450000,
    "海南": 460000, "重庆": 500000, "四川": 510000, "贵州": 520000, "云南": 530000,
    "西藏": 540000, "陕西": 610000, "甘肃": 620000, "青海": 630000, "宁夏": 640000,
    "新疆": 650000, "台湾": 710000, "香港": 810000, "澳门": 820000,
}

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


async def _load_geodata(adcode: int) -> dict | None:
    """跟 api/geo.py 共用同一份缓存目录:缺失时下载一次永久缓存,不重复造轮子。"""
    GEODATA_DIR.mkdir(exist_ok=True)
    path = GEODATA_DIR / f"{adcode}.json"
    if not path.exists():
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(DATAV_URL.format(code=f"{adcode}_full"))
                if r.status_code != 200:
                    r = await client.get(DATAV_URL.format(code=adcode))
                if r.status_code != 200:
                    return None
                path.write_bytes(r.content)
        except httpx.HTTPError:
            return None
    return json.loads(path.read_text())


def _point_in_ring(lng: float, lat: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate(p[:2] for p in ring):
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_intersect = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lng < x_intersect:
                inside = not inside
        j = i
    return inside


def _point_in_polygon(lng: float, lat: float, polygon: list) -> bool:
    if not polygon or not _point_in_ring(lng, lat, polygon[0]):
        return False
    return not any(_point_in_ring(lng, lat, hole) for hole in polygon[1:])


def _point_in_geometry(lng: float, lat: float, geometry: dict) -> bool:
    if geometry["type"] == "Polygon":
        return _point_in_polygon(lng, lat, geometry["coordinates"])
    if geometry["type"] == "MultiPolygon":
        return any(_point_in_polygon(lng, lat, poly) for poly in geometry["coordinates"])
    return False


async def resolve_city(province_name: str, lat: float, lng: float) -> str | None:
    """省级质心归属基础上再细化到市——点在多边形判断,几何数据跟地图渲染共用同一份缓存,不额外调用任何API。"""
    adcode = PROVINCE_ADCODE.get(province_name)
    if not adcode:
        return None
    data = await _load_geodata(adcode)
    if not data:
        return None
    for feat in data["features"]:
        if _point_in_geometry(lng, lat, feat["geometry"]):
            return feat["properties"]["name"]
    best, best_d = None, float("inf")
    for feat in data["features"]:
        center = feat["properties"].get("center")
        if not center:
            continue
        d = haversine_km(lat, lng, center[1], center[0])
        if d < best_d:
            best, best_d = feat["properties"]["name"], d
    return best


async def macro_of_province(session: AsyncSession, province: Region) -> Region | None:
    if province.parent_id is None:
        return None
    return await session.get(Region, province.parent_id)

"""最近的城市。

只用在审核页和揭晓页:审核时要能一眼看出坐标标没标对("俄罗斯·北部"看不出来),
玩家猜完了看到"拍摄于 Tbilisi 附近 3 公里"也比只看见国名有意思。

**不给提示用**——提示到城市就等于报答案。

数据是 GeoNames 的 cities15000(人口一万五以上,3.4 万条,CC BY 4.0)。
中文名那一栏没要:数据里混着繁体,还把 Cape Town 标成"好望角镇",错的比对的显眼。
"""
import functools
from pathlib import Path

from app.services.scoring import haversine_km

DATA = Path(__file__).resolve().parents[2] / "geodata" / "cities.tsv"
# 超过这个距离就别提城市了:荒野里硬扯一个几百公里外的城市名只会误导
MAX_KM = 120.0


@functools.lru_cache(maxsize=1)
def _cities() -> list[tuple[str, float, float, str, int]]:
    rows = []
    for line in DATA.read_text(encoding="utf-8").splitlines():
        name, lat, lng, cc, pop = line.split("\t")
        rows.append((name, float(lat), float(lng), cc, int(pop)))
    return rows


def nearest_city(lat: float, lng: float) -> tuple[str, float] | None:
    """→ (城市名, 距离公里)。附近没有城市就返回 None。"""
    # 先用经纬度粗筛,3.4 万条全算 haversine 太浪费;1.5 度约 165 公里,覆盖得住 MAX_KM
    span = 1.5
    near = [c for c in _cities() if abs(c[1] - lat) <= span and abs(c[2] - lng) <= span * 2]
    if not near:
        return None
    name, clat, clng, _, _ = min(near, key=lambda c: haversine_km(lat, lng, c[1], c[2]))
    distance = haversine_km(lat, lng, clat, clng)
    return (name, round(distance, 1)) if distance <= MAX_KM else None


def find_city(
    name: str, near: tuple[float, float] | None = None, cc: str | None = None
) -> tuple[float, float] | None:
    """按名字查城市坐标。同名城市很多(光 Springfield 就一堆),先按国家收窄,再用大致位置消歧。

    模型认得出"布哈拉",却报不准经纬度——地名靠它,坐标靠这张表。
    国家一定要收:线上出现过模型自己说"这是毛里求斯",坐标却落到阿曼去,
    差了四千多公里,玩家看到的是一段自相矛盾的话。
    """
    key = name.strip().lower()
    if not key:
        return None
    pool = _cities()
    if cc:
        same_country = [c for c in pool if c[3] == cc.upper()]
        # 模型说的国家在表里没有这座城市,那就退到这个国家本身,
        # 总好过跑到地球另一头去找个同名的
        pool = same_country or pool
    hits = [c for c in pool if c[0].lower() == key]
    if not hits:
        hits = [c for c in pool if key in c[0].lower() and len(key) >= 4]
    if not hits:
        return country_center(cc) if cc else None
    if near:
        best = min(hits, key=lambda c: haversine_km(near[0], near[1], c[1], c[2]))
    else:
        best = max(hits, key=lambda c: c[4])  # 没有参考点就取人口最多的那个
    return best[1], best[2]


def country_center(cc: str) -> tuple[float, float] | None:
    """一个国家的落点,取它人口最多的那座城市。只在城市名查不到时兜底。"""
    hits = [c for c in _cities() if c[3] == cc.upper()]
    if not hits:
        return None
    best = max(hits, key=lambda c: c[4])
    return best[1], best[2]

"""最近的城市 / 按名字查城市。

用在两处:
  - 审核页和揭晓页——"离 Suzdal 2 公里"一眼看得出坐标标没标对,"俄罗斯·北部"看不出来;
  - 把 AI 报的地名换成坐标——地名它记得住,经纬度是编的。

**不给提示用**:提示到城市就等于报答案。

数据是 GeoNames 的 cities500(人口 500 以上或是行政驻地,23.6 万条,CC BY 4.0)。
原来用的是 cities15000,只有 3.4 万条,AI 报的乡镇、海滩、村子一大半查不到,
查不到就退到"这个国家最大的城市",于是它嘴上说乌鲁木齐、针插在上海。
中文名那一栏没要:数据里混着繁体,还把 Cape Town 标成"好望角镇",错的比对的显眼。
"""
import functools
import unicodedata
from pathlib import Path

from app.services.scoring import haversine_km

DATA = Path(__file__).resolve().parents[2] / "geodata" / "cities.tsv"
# 超过这个距离就别提城市了:荒野里硬扯一个几百公里外的城市名只会误导
MAX_KM = 120.0

# 表里写本地拼写(Ürümqi、Xi'an、Port-Louis),模型打的是 Urumqi、Xian、Port Louis。
# 不把这些差别抹平,两边就永远对不上——线上西安因此被模糊匹配成了襄阳。
_FOLD = str.maketrans(
    {"ø": "o", "ł": "l", "đ": "d", "ß": "ss", "æ": "ae", "œ": "oe",
     "ı": "i", "ð": "d", "þ": "th", "-": " ", "_": " "}
)
_DROP = "'’‘`´"


def fold(name: str) -> str:
    """去掉变音符号、撇号和连字符,好让 Urumqi 认出 Ürümqi、Port Louis 认出 Port-Louis。"""
    lowered = name.strip().lower().translate(_FOLD)
    kept = "".join(
        c for c in unicodedata.normalize("NFKD", lowered)
        if not unicodedata.combining(c) and c not in _DROP
    )
    return " ".join(kept.split())


@functools.lru_cache(maxsize=1)
def _cities() -> list[tuple[str, float, float, str, int]]:
    """(显示名, 纬度, 经度, 国家代码, 人口)"""
    rows = []
    for line in DATA.read_text(encoding="utf-8").splitlines():
        name, _ascii, lat, lng, cc, pop = line.split("\t")
        rows.append((name, float(lat), float(lng), cc, int(pop)))
    return rows


@functools.lru_cache(maxsize=1)
def _folded() -> list[tuple[str, str, float, float, str, int]]:
    """(折叠后的本地名, 折叠后的 ascii 名, 纬度, 经度, 国家代码, 人口)"""
    rows = []
    for line in DATA.read_text(encoding="utf-8").splitlines():
        name, ascii_name, lat, lng, cc, pop = line.split("\t")
        rows.append((fold(name), fold(ascii_name) if ascii_name else "", float(lat), float(lng), cc, int(pop)))
    return rows


def nearest_city(lat: float, lng: float) -> tuple[str, float] | None:
    """→ (城市名, 距离公里)。附近没有城市就返回 None。"""
    # 先用经纬度粗筛,二十多万条全算 haversine 太浪费;1.5 度约 165 公里,覆盖得住 MAX_KM
    span = 1.5
    near = [c for c in _cities() if abs(c[1] - lat) <= span and abs(c[2] - lng) <= span * 2]
    if not near:
        return None
    name, clat, clng, _, _ = min(near, key=lambda c: haversine_km(lat, lng, c[1], c[2]))
    distance = haversine_km(lat, lng, clat, clng)
    return (name, round(distance, 1)) if distance <= MAX_KM else None


def nearest_cc(lat: float, lng: float) -> str | None:
    """这个坐标落在哪个国家(按最近的城市算)。用来判断模型给的经纬度可不可信。"""
    span = 2.0
    near = [c for c in _cities() if abs(c[1] - lat) <= span and abs(c[2] - lng) <= span * 2]
    if not near:
        return None
    return min(near, key=lambda c: haversine_km(lat, lng, c[1], c[2]))[3]


def find_city(
    name: str, near: tuple[float, float] | None = None, cc: str | None = None
) -> tuple[float, float] | None:
    """按名字查城市坐标。同名的很多(光 Springfield 就一堆),先按国家收窄,再用大致位置消歧。

    国家一定要收:线上出现过模型自己说"这是毛里求斯",坐标却落到阿曼去,差了四千多公里,
    玩家看到的是一段自相矛盾的话。查不到就返回 None,由调用方决定怎么办——
    这里不再自作主张退到"这个国家最大的城市",那会把针插到一个 AI 根本没提过的城市上。
    """
    key = fold(name)
    if not key:
        return None
    pool = _folded()
    if cc:
        pool = [c for c in pool if c[4] == cc.upper()] or pool
    hits = [c for c in pool if key in (c[0], c[1])]
    if not hits and len(key) >= 5:
        # 退一步做包含匹配,但要求长一点,免得 "xian" 命中 "xianyang"
        hits = [c for c in pool if key in c[0] or (c[1] and key in c[1])]
    if not hits:
        return None
    if near:
        best = min(hits, key=lambda c: haversine_km(near[0], near[1], c[2], c[3]))
    else:
        best = max(hits, key=lambda c: c[5])  # 没有参考点就取人口最多的那个
    return best[2], best[3]


def country_fallback(cc: str, near: tuple[float, float] | None = None) -> tuple[float, float] | None:
    """实在查不到城市时的落点:这个国家里离模型自己给的坐标最近的城市。"""
    hits = [c for c in _cities() if c[3] == cc.upper()]
    if not hits:
        return None
    if near:
        best = min(hits, key=lambda c: haversine_km(near[0], near[1], c[1], c[2]))
    else:
        best = max(hits, key=lambda c: c[4])
    return best[1], best[2]

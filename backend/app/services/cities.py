"""最近的城市。

只用在审核页和揭晓页:审核时要能一眼看出坐标标没标对("俄罗斯·北部"看不出来),
玩家猜完了看到"拍摄于 Tbilisi 附近 3 公里"也比只看见国名有意思。

**不给提示用**——提示到城市就等于报答案。

数据是 GeoNames 的 cities15000(人口一万五以上,3.4 万条,CC BY 4.0)。
中文名那一栏没要:数据里混着繁体,还把 Cape Town 标成"好望角镇",错的比对的显眼。
"""
import functools
import unicodedata
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


# GeoNames 用本地拼写:Ürümqi、Malmö、Kraków。模型报的是 Urumqi、Malmo、Krakow,
# 直接比对一个都对不上——三万四千条里有七千条带变音符号。
# 之前查不到就退到"这个国家最大的城市",乌鲁木齐因此被标到了上海,差 3765 公里。
_FOLD = str.maketrans({"ø": "o", "ł": "l", "đ": "d", "ß": "ss", "æ": "ae", "œ": "oe", "ı": "i", "ð": "d", "þ": "th"})


def _fold(name: str) -> str:
    """去掉变音符号和撇号,好让 Urumqi 认出 Ürümqi、Xian 认出 Xi’an。

    撇号必须去:表里写的是弯撇号 Xi’an,模型打的是直撇号或者干脆不打,
    对不上就退到模糊匹配,把西安匹配成了襄阳。
    """
    lowered = name.strip().lower().translate(_FOLD)
    stripped = unicodedata.normalize("NFKD", lowered)
    return "".join(c for c in stripped if not unicodedata.combining(c) and c not in "'’‘`´")


@functools.lru_cache(maxsize=1)
def _folded() -> list[tuple[str, float, float, str, int]]:
    return [(_fold(n), lat, lng, cc, pop) for n, lat, lng, cc, pop in _cities()]


def find_city(
    name: str, near: tuple[float, float] | None = None, cc: str | None = None
) -> tuple[float, float] | None:
    """按名字查城市坐标。同名城市很多(光 Springfield 就一堆),先按国家收窄,再用大致位置消歧。

    模型认得出"布哈拉",却报不准经纬度——地名靠它,坐标靠这张表。
    国家一定要收:线上出现过模型自己说"这是毛里求斯",坐标却落到阿曼去,
    差了四千多公里,玩家看到的是一段自相矛盾的话。
    """
    key = _fold(name)
    if not key:
        return None
    pool = _folded()
    if cc:
        same_country = [c for c in pool if c[3] == cc.upper()]
        # 模型说的国家在表里没有这座城市,那就退到这个国家里离它自己给的坐标最近的城市,
        # 总好过跑到地球另一头找个同名的,也好过一律丢到首都去
        pool = same_country or pool
    hits = [c for c in pool if c[0] == key]
    if not hits:
        hits = [c for c in pool if key in c[0] and len(key) >= 4]
    if not hits:
        return country_fallback(cc, near) if cc else None
    if near:
        best = min(hits, key=lambda c: haversine_km(near[0], near[1], c[1], c[2]))
    else:
        best = max(hits, key=lambda c: c[4])  # 没有参考点就取人口最多的那个
    return best[1], best[2]


def country_fallback(cc: str, near: tuple[float, float] | None = None) -> tuple[float, float] | None:
    """城市名查不到时的落点:这个国家里离模型自己给的坐标最近的城市。

    模型的经纬度不准,但通常大方向没错;拿它在正确的国家里挑个最近的,
    比一律丢到人口最多的城市强得多。没给坐标才退回最大的城市。
    """
    hits = [c for c in _cities() if c[3] == cc.upper()]
    if not hits:
        return None
    if near:
        best = min(hits, key=lambda c: haversine_km(near[0], near[1], c[1], c[2]))
    else:
        best = max(hits, key=lambda c: c[4])
    return best[1], best[2]

"""判分引擎——幻觉隔离原则:此模块是纯程序,永远不经过AI。"""
import math

MAX_SCORE = 5000
PERFECT_KM = 0.25
DECAY_KM = 400.0  # 中国尺度衰减常数;将来按 Region 配置(世界地图用 ~1500)

HINT_MULTIPLIERS = {1: 1.0, 2: 0.8, 3: 0.6, 4: 0.4}

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def score_from_distance(distance_km: float, decay_km: float = DECAY_KM) -> int:
    if distance_km <= PERFECT_KM:
        return MAX_SCORE
    return round(MAX_SCORE * math.exp(-distance_km / decay_km))


def hint_multiplier(hints_mask: int) -> float:
    m = 1.0
    for level, mult in HINT_MULTIPLIERS.items():
        if hints_mask & (1 << (level - 1)):
            m = min(m, mult)
    return m


def final_score(distance_km: float, hints_mask: int, decay_km: float = DECAY_KM) -> int:
    return round(score_from_distance(distance_km, decay_km) * hint_multiplier(hints_mask))

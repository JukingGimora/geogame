"""判分引擎——幻觉隔离原则:此模块是纯程序,永远不经过AI。"""
import math

MAX_SCORE = 5000
PERFECT_KM = 0.25
DECAY_KM = 400.0  # 兜底值(老数据没存尺度时用)

# 尺子跟着题池走:全球混着玩时猜对国家就算好,只玩一个岛时差 30 公里就该扣分。
# 写死几档 if/else 以后没人维护得了,所以由池子自己的地理尺度推出来。
SCALE_FACTOR = 0.4
MIN_DECAY_KM = 300.0   # 太平洋那 22 张全在斐济一个岛上,尺度只有 17 公里,不兜底会苛刻到离谱
MAX_DECAY_KM = 1500.0  # 全球池子的上限,和 GeoGuessr 世界模式的量级一致
MISS_FACTOR = 1.5      # 掉命线 = 判分尺度 × 它

# 每多买一级扣两成:①免费 ②0.8 ③0.6 ④0.4 ⑤0.2。一条公式,加一级不用改表
HINT_STEP = 0.2

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


def pool_decay_km(points: list[tuple[float, float]]) -> float:
    """题池的地理尺度 → 这一局的判分尺度。

    尺度取"每张照片到池子重心的平均距离":比包围盒稳,少数几张远的照片不会把它拉爆。
    """
    if len(points) < 2:
        return MIN_DECAY_KM
    x = y = z = 0.0
    for lat, lng in points:
        p, l = math.radians(lat), math.radians(lng)
        x += math.cos(p) * math.cos(l)
        y += math.cos(p) * math.sin(l)
        z += math.sin(p)
    n = len(points)
    clat = math.degrees(math.atan2(z / n, math.hypot(x / n, y / n)))
    clng = math.degrees(math.atan2(y / n, x / n))
    spread = sum(haversine_km(lat, lng, clat, clng) for lat, lng in points) / n
    return min(MAX_DECAY_KM, max(MIN_DECAY_KM, spread * SCALE_FACTOR))


def miss_km(decay_km: float) -> float:
    """超过这个距离掉一条命。跟着判分尺度走,不用单独维护一个常量。"""
    return decay_km * MISS_FACTOR


def hint_multiplier(hints_mask: int) -> float:
    """按买到的最贵那一级算。买了④就是四折,再买⑤就是二折。"""
    highest = hints_mask.bit_length()
    return round(max(0.0, 1.0 - HINT_STEP * (highest - 1)), 2) if highest else 1.0


def final_score(distance_km: float, hints_mask: int, decay_km: float = DECAY_KM) -> int:
    return round(score_from_distance(distance_km, decay_km) * hint_multiplier(hints_mask))

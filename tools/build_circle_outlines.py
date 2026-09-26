"""把文化圈的边界线从国家轮廓里算出来,写回 geodata/world.json。

手画的九个多边形怎么调都对不上海岸线——太平洋圈那个五边形整个浮在海上,
非洲圈的边压着大西洋。可 world.json 里每个国家本来就标着属于哪个圈,
边界线不该另外画一遍,它就是"同一个圈的国家合起来"的外沿。

做法:把同圈的轮廓外扩一点合并(隔着海峡的邻国、成串的岛才连得成一片),
再收回来一点,最后抽稀。外扩的度数是唯一的手调项,大了会把无关的地方圈进去,
小了岛链连不起来。

跨接缝(地图以 150°E 为中心,接缝落在大西洋 -30°)的圈要先把经度展开成连续的,
否则巴西、格陵兰会被算成横跨整张图的一条带子。

    python3 tools/build_circle_outlines.py

跑完 world.json 会多出一个 circles 字段,前端直接读,不用改接口。
"""
import json
from pathlib import Path

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

WORLD = Path(__file__).resolve().parents[1] / "backend" / "geodata" / "world.json"

CENTER_LNG = 150  # 跟前端 WorldMap.vue 保持一致
GROW = 2.2        # 外扩多少度:够把马六甲两岸、加勒比的岛链连起来
SHRINK = 1.0      # 再收回来,线就不会离海岸太远
SIMPLIFY = 0.35   # 抽稀容差,主要是为了让文件小到能塞进小程序包
# 比这小的碎块不画:手机上一度约一个像素,再小的圈只是个点,读不出是什么
MIN_AREA = 8.0


def rel(lng: float) -> float:
    """真实经度 → 以中心经线为 0 的相对经度,跟前端同一套。"""
    return ((lng - CENTER_LNG + 540) % 360) - 180


def unrel(x: float) -> float:
    return ((x + CENTER_LNG + 540) % 360) - 180


def unwrapped(ring: list[list[float]]) -> list[tuple[float, float]]:
    """把一个环的相对经度接成连续的,跨接缝的国家才不会被拉平。"""
    out: list[tuple[float, float]] = []
    prev: float | None = None
    for lng, lat in ring:
        x = rel(lng)
        if prev is not None:
            while x - prev > 180:
                x -= 360
            while prev - x > 180:
                x += 360
        out.append((x, lat))
        prev = x
    return out


def wrapped_back(poly: Polygon) -> list[Polygon]:
    """把展开过的多边形按接缝切开,每片各自挪回 [-180, 180]。"""
    out: list[Polygon] = []
    for lo in (-540, -180, 180, 540):
        piece = poly.intersection(box(lo, -90, lo + 360, 90))
        if piece.is_empty:
            continue
        shift = -(lo + 180)
        for part in (piece.geoms if hasattr(piece, "geoms") else [piece]):
            if isinstance(part, Polygon) and not part.is_empty:
                out.append(Polygon([(x + shift, y) for x, y in part.exterior.coords]))
    return out


def main() -> None:
    data = json.loads(WORLD.read_text(encoding="utf-8"))

    # 南极洲要丢掉。它在等距圆柱投影下摊成横贯全图的一条带子,
    # 而且按最近邻被判进了非洲文化圈,连带把非洲的边界线拽到图的最下沿。
    # 那儿不会有照片,不画。
    before = len(data["features"])
    data["features"] = [
        f for f in data["features"] if max(p[1] for r in f["r"] for p in r) > -60
    ]
    if before != len(data["features"]):
        print(f"丢掉 {before - len(data['features'])} 块南极")

    by_circle: dict[str, list[Polygon]] = {}
    for f in data["features"]:
        for ring in f["r"]:
            pts = unwrapped(ring)
            if len(pts) < 3:
                continue
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            by_circle.setdefault(f["c"], []).append(poly)

    circles: dict[str, list[list[list[float]]]] = {}
    for name, polys in by_circle.items():
        blob = unary_union([p.buffer(GROW) for p in polys]).buffer(-SHRINK).simplify(SIMPLIFY)
        parts = blob.geoms if isinstance(blob, MultiPolygon) else [blob]
        loops = []
        for part in parts:
            # 展开经度是为了合并,合并完得切回来:一圈跨过接缝再取模,
            # 点的顺序会绕成个死结,重心能算到经度 2485 去
            for piece in wrapped_back(part):
                if piece.area < MIN_AREA:
                    continue
                loops.append([[round(unrel(x), 2), round(y, 2)] for x, y in piece.exterior.coords])
        circles[name] = loops
        print(f"{name}: {len(loops)} 块, {sum(len(l) for l in loops)} 个点")

    data["circles"] = circles
    WORLD.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\n写回 {WORLD} ({WORLD.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

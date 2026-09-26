"""把世界切成九块文化圈,写回 geodata/world.json。

参考图的画法是:红线从图的一边穿到另一边、横过大洋,把整张地图分成九块——
每个点只属于一块,所以不可能有交集。之前那版是"每个圈的国家轮廓往外胀一点再合并",
相邻的圈各胀各的,接壤处必然叠上两三度宽的一条,总共 1044 平方度的重叠,调参数解决不了。

这版按**游戏自己的判定规则**切。`locate()` 判断一个坐标属于哪个圈,用的是"离哪个锚点最近",
那么两个圈真正的分界线就是锚点之间的中垂线,也就是 Voronoi 图。好处:

  - 数学上不可能有交集,也不会有缝;
  - 地图上那条线就是游戏真正在用的规则,玩家不会"画在圈里却判成别的圈";
  - 不用手调任何参数。

Voronoi 的原始边界全是直线拐角,像摔碎的玻璃,不好认。所以再过一遍 Chaikin 割角:
同一条边在两侧用的是同一串顶点,割角是确定性的,两边割出来还是同一条线,分区不会破。

    python3 tools/build_circle_outlines.py --svg 预览.svg   # 先看图
    python3 tools/build_circle_outlines.py                  # 满意了再写回
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

import shapely
from shapely.geometry import MultiPoint, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.circles import ANCHORS, COUNTRIES  # noqa: E402

WORLD = Path(__file__).resolve().parents[1] / "backend" / "geodata" / "world.json"

CENTER_LNG = 150  # 跟前端 WorldMap.vue 保持一致
LAT_MIN, LAT_MAX = -58.0, 84.0  # 跟前端的取景一致:南极不画
SMOOTH_ROUNDS = 5  # 割几轮角。轮数越多越圆,也越离锚点的真实中垂线远
SIMPLIFY = 0.4     # 割角会把点数翻几倍,抽稀压回来,免得小程序包吃不消
# 比这小的碎块不画。西欧本该是三块(北美、欧洲、澳新),不清理会多出一片
# 地中海里的碎片(马耳他自己的格子被海隔断了),东欧也会多出一片远东的碎渣
MIN_BLOCK = 200.0

CIRCLE_COLORS = {
    "东亚": "#c9bd8f", "东南亚": "#7fae86", "南亚": "#c98f6a", "伊斯兰": "#c2564e",
    "西欧": "#6f93c4", "东欧": "#4a7fb5", "非洲": "#c98a3c", "拉美": "#8f6ac9",
    "太平洋": "#5fb0a8",
}


def rel(lng: float) -> float:
    """真实经度 → 以中心经线为 0 的相对经度,跟前端同一套。"""
    return ((lng - CENTER_LNG + 540) % 360) - 180


def unrel(x: float) -> float:
    return ((x + CENTER_LNG + 540) % 360) - 180


def chaikin(ring: list[tuple[float, float]], rounds: int) -> list[tuple[float, float]]:
    """割角:每条边取 1/4 和 3/4 两点代替原顶点,越割越圆。闭合环,首尾相连。"""
    pts = ring[:-1] if ring[0] == ring[-1] else ring[:]
    for _ in range(rounds):
        out = []
        for i, (x1, y1) in enumerate(pts):
            x2, y2 = pts[(i + 1) % len(pts)]
            out.append((x1 * 0.75 + x2 * 0.25, y1 * 0.75 + y2 * 0.25))
            out.append((x1 * 0.25 + x2 * 0.75, y1 * 0.25 + y2 * 0.75))
        pts = out
    return pts + [pts[0]]


def partition(smooth: bool = True) -> dict[str, object]:
    """把整张图切成九块。返回 {文化圈: 形状},形状之间不重叠、不留缝。"""
    seeds = [(rel(lng), lat, circle) for _, lat, lng, circle in COUNTRIES]
    seeds += [(rel(lng), lat, circle) for _, lat, lng, circle in ANCHORS]

    # 接缝在 rel ±180。把点向两侧各复制一份,接缝附近的格子才算得对,算完再裁回来——
    # 不这么做,最左和最右那两块会被切成互不相干的半块。
    spread = [(x + dx, y, c) for x, y, c in seeds for dx in (-360, 0, 360)]
    cells = shapely.voronoi_polygons(
        MultiPoint([(x, y) for x, y, _ in spread]),
        extend_to=box(-540, LAT_MIN - 40, 540, LAT_MAX + 40),
        ordered=True,
    )
    view = box(-180, LAT_MIN, 180, LAT_MAX)

    parts: dict[str, list[Polygon]] = {}
    for cell, (_, _, circle) in zip(cells.geoms, spread):
        piece = cell.intersection(view)
        if not piece.is_empty:
            parts.setdefault(circle, []).append(piece)

    out = {}
    for circle, polys in parts.items():
        shape = unary_union(polys).simplify(SIMPLIFY)
        if smooth:
            shape = _smooth(shape)
        out[circle] = shape
    return out


def _smooth(shape):
    polys = shape.geoms if hasattr(shape, "geoms") else [shape]
    rounded = []
    for poly in polys:
        if not isinstance(poly, Polygon) or poly.area < MIN_BLOCK:
            continue
        ring = chaikin(list(poly.exterior.coords), SMOOTH_ROUNDS)
        p = Polygon(ring).simplify(SIMPLIFY)
        if not p.is_valid:
            p = p.buffer(0)
        if not p.is_empty:
            rounded.append(p)
    return unary_union(rounded) if len(rounded) > 1 else rounded[0]


def rings(shape) -> list[list[list[float]]]:
    """形状 → 若干个环,经度换回真实值。"""
    polys = shape.geoms if hasattr(shape, "geoms") else [shape]
    out = []
    for poly in polys:
        if not isinstance(poly, Polygon) or poly.area < MIN_BLOCK:
            continue
        out.append([[round(unrel(x), 2), round(y, 2)] for x, y in poly.exterior.coords])
    return out


def write_svg(regions: dict, path: Path) -> None:
    """出预览图:分区打底,真实陆地压在上面,好看出线切得对不对。"""
    w = 1300
    h = int(w * (LAT_MAX - LAT_MIN) / 360)

    def pt(x, y):
        return f"{(x + 180) / 360 * w:.1f},{(LAT_MAX - y) / (LAT_MAX - LAT_MIN) * h:.1f}"

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}"><rect width="{w}" height="{h}" fill="#0f0c08"/>']

    # 陆地按文化圈上色,跟线上一样;分区只画线,不铺底
    world = json.loads(WORLD.read_text(encoding="utf-8"))
    for f in world["features"]:
        colour = CIRCLE_COLORS.get(f["c"], "#6b5f4a")
        for ring in f["r"]:
            pts, prev, broke = [], None, False
            for lng, lat in ring:
                x = rel(lng)
                if prev is not None and abs(x - prev) > 180:
                    broke = True
                    break
                pts.append(pt(x, lat))
                prev = x
            if not broke and len(pts) >= 3:
                svg.append(f'<polygon points="{" ".join(pts)}" fill="{colour}" '
                           f'fill-opacity="0.55" stroke="{colour}" stroke-opacity="0.55"/>')

    for name, shape in regions.items():
        colour = CIRCLE_COLORS.get(name, "#888")
        for poly in (shape.geoms if hasattr(shape, "geoms") else [shape]):
            if poly.area < MIN_BLOCK:
                continue
            d = " ".join(pt(x, y) for x, y in poly.exterior.coords)
            svg.append(f'<polygon points="{d}" fill="none" stroke="{colour}" stroke-width="2.2"/>')

    for name, shape in regions.items():
        c = shape.representative_point()
        x = (c.x + 180) / 360 * w
        y = (LAT_MAX - c.y) / (LAT_MAX - LAT_MIN) * h
        svg.append(f'<text x="{x:.0f}" y="{y:.0f}" fill="#fff" font-size="18" '
                   f'text-anchor="middle" stroke="#0f0c08" stroke-width="3" '
                   f'paint-order="stroke">{name}</text>')
    svg.append("</svg>")
    path.write_text("\n".join(svg), encoding="utf-8")
    print(f"预览图 → {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", help="只出预览图,不改 world.json")
    ap.add_argument("--raw", action="store_true", help="不割角,看原始的 Voronoi 直线边界")
    args = ap.parse_args()

    regions = partition(smooth=not args.raw)
    overlap = sum(
        regions[a].intersection(regions[b]).area for a, b in itertools.combinations(regions, 2)
    )
    print(f"九块,重叠面积 {overlap:.1f} 平方度")
    for name, shape in regions.items():
        rs = rings(shape)
        print(f"  {name}: {len(rs)} 块, {sum(len(r) for r in rs)} 个点")

    if args.svg:
        write_svg(regions, Path(args.svg))
        return

    data = json.loads(WORLD.read_text(encoding="utf-8"))
    data["circles"] = {name: rings(shape) for name, shape in regions.items()}
    WORLD.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\n写回 {WORLD} ({WORLD.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

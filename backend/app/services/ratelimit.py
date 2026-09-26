"""按 IP 的简易限速。

接口本来就在公网上(小程序也走同一套),H5 一放开只是让写脚本更容易。
最该挡的三件:批量注册刷号、灌垃圾图、把单机 SQLite 打满。

单进程内存计数就够了——真到需要多进程的量级,该换的是数据库不是这个模块。
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# 路径前缀 → (允许次数, 时间窗口秒)
# 阈值放得比"正常人"宽很多:一个教室的学生共用一个出口 IP,按人估会把整班挡在门外。
# 这里只拦脚本级别的流量,真正的配额按账号算(见 photos.py 的每日上传上限)。
# 顺序有意义:取第一个匹配上的前缀,所以更具体的路径要排在前面
LIMITS: dict[str, tuple[int, int]] = {
    # 批量导入本来就是几百张连着传,跟后台的防撞库阈值不是一回事
    "/api/v1/admin/photos/import": (600, 300),
    "/api/v1/auth/guest": (100, 600),
    "/api/v1/photos": (60, 3600),
    "/api/v1/runs": (120, 300),
    # 后台只防跑飞的脚本;猜口令由 admin_gate 单独挡,审一轮图要点几百下
    "/api/v1/admin": (1200, 300),
}

# 口令猜错多少次就把这个 IP 关在门外
ADMIN_FAIL_QUOTA = 10
ADMIN_FAIL_WINDOW = 900

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # 走的是隧道,真实 IP 在转发头里
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit(request: Request) -> None:
    rule = next(((p, v) for p, v in LIMITS.items() if request.url.path.startswith(p)), None)
    if not rule:
        return
    prefix, (quota, window) = rule
    key = (prefix, _client_ip(request))
    now = time.monotonic()
    hits = _hits[key]
    while hits and now - hits[0] > window:
        hits.popleft()
    if len(hits) >= quota:
        raise HTTPException(429, "too_many_requests")
    hits.append(now)


def admin_gate(request: Request, ok: bool) -> None:
    """后台口令的失败计数。

    猜对的请求不计数:审图是连着点几百下的活,不能跟撞库共用一个额度
    (之前共用,结果审到一半整个后台 429)。要挡的只有猜错的那些。
    """
    key = ("admin-fail", _client_ip(request))
    now = time.monotonic()
    hits = _hits[key]
    while hits and now - hits[0] > ADMIN_FAIL_WINDOW:
        hits.popleft()
    if len(hits) >= ADMIN_FAIL_QUOTA:
        raise HTTPException(429, "too_many_requests")
    if not ok:
        hits.append(now)

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
LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/auth/guest": (100, 600),
    "/api/v1/photos": (60, 3600),
    "/api/v1/runs": (120, 300),
    "/api/v1/admin": (60, 300),  # 后台口令没有失败次数限制,先用限速兜着
}

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

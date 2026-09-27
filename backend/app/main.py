import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, circles, events, feedback, geo, leaderboard, photos, play, regions, users
from app.config import settings
from app.db import async_session_maker, init_db
from app.services.geo import seed_regions
from app.services.notify import pending_digest_loop
from app.services.ratelimit import rate_limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session_maker() as session:
        await seed_regions(session)
    digest = asyncio.create_task(pending_digest_loop())
    yield
    digest.cancel()


app = FastAPI(title="geogame", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
LIMITED = [Depends(rate_limit)]
app.include_router(auth.router, prefix=API, dependencies=LIMITED)
app.include_router(regions.router, prefix=API, dependencies=LIMITED)
app.include_router(circles.router, prefix=API, dependencies=LIMITED)
app.include_router(users.router, prefix=API, dependencies=LIMITED)
app.include_router(geo.router, prefix=API, dependencies=LIMITED)
app.include_router(leaderboard.router, prefix=API, dependencies=LIMITED)
app.include_router(feedback.router, prefix=API, dependencies=LIMITED)
app.include_router(events.router, prefix=API, dependencies=LIMITED)
app.include_router(photos.router, prefix=API, dependencies=LIMITED)
app.include_router(play.router, prefix=API, dependencies=LIMITED)
app.include_router(admin.router, prefix=API, dependencies=LIMITED)

app.mount("/uploads", StaticFiles(directory=str(settings.upload_path)), name="uploads")
# 网页版:同一份产物挂在两个路径下,`/en` 是英文、`/zh` 是中文。
# 语言写进路径而不是只用查询参数,是为了能直接把链接发给人——
# 发一个 ?lang=zh 出去,对方一看就知道这是"改过设置的英文站",不像个中文站。
# 能这么挂是因为构建用的相对资源路径(vite base: "./")加 hash 路由,
# 换成绝对 base 或 history 路由,第二个挂载点就会 404。
WEB_DIR = Path(__file__).parent / "static" / "web"
# 目录不在也要能起:网页版产物是 rsync 上去的,不进 git。少了它只该是网页打不开,
# 不该让整个后端起不来——所有接口跟着一起挂,代价完全不对等
WEB_DIR.mkdir(parents=True, exist_ok=True)


def _web_index() -> FileResponse:
    # 不缓存入口页:脚本名带哈希会变,但 index.html 被浏览器缓存住的话,
    # 新版发出去了用户还在跑旧的——排查这事白白花过一轮
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/en/")
async def web_index_en():
    return _web_index()


@app.get("/zh/")
async def web_index_zh():
    return _web_index()


for _lang in ("en", "zh"):
    app.mount(f"/{_lang}", StaticFiles(directory=str(WEB_DIR), html=True), name=f"web-{_lang}")


@app.get("/admin")
async def admin_page():
    # 不缓存:否则改了审核页要手工强刷才能看到,很容易误判成"功能没生效"
    return FileResponse(
        Path(__file__).parent / "static" / "admin.html",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/health")
async def health():
    return {"ok": True}

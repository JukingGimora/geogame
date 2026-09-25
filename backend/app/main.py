import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, circles, events, feedback, geo, leaderboard, photos, play, regions
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
app.include_router(geo.router, prefix=API, dependencies=LIMITED)
app.include_router(leaderboard.router, prefix=API, dependencies=LIMITED)
app.include_router(feedback.router, prefix=API, dependencies=LIMITED)
app.include_router(events.router, prefix=API, dependencies=LIMITED)
app.include_router(photos.router, prefix=API, dependencies=LIMITED)
app.include_router(play.router, prefix=API, dependencies=LIMITED)
app.include_router(admin.router, prefix=API, dependencies=LIMITED)

app.mount("/uploads", StaticFiles(directory=str(settings.upload_path)), name="uploads")
@app.get("/h5test/")
async def h5_index():
    # 不缓存入口页:脚本名带哈希会变,但 index.html 被浏览器缓存住的话,
    # 新版发出去了用户还在跑旧的——排查这事白白花过一轮
    return FileResponse(
        Path(__file__).parent / "static" / "h5test" / "index.html",
        headers={"Cache-Control": "no-cache"},
    )


app.mount(
    "/h5test",
    StaticFiles(directory=str(Path(__file__).parent / "static" / "h5test"), html=True),
    name="h5test",
)


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

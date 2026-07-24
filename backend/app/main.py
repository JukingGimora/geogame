from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, events, feedback, geo, leaderboard, photos, play, regions
from app.config import settings
from app.db import async_session_maker, init_db
from app.services.geo import seed_regions


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session_maker() as session:
        await seed_regions(session)
    yield


app = FastAPI(title="geogame", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(regions.router, prefix=API)
app.include_router(geo.router, prefix=API)
app.include_router(leaderboard.router, prefix=API)
app.include_router(feedback.router, prefix=API)
app.include_router(events.router, prefix=API)
app.include_router(photos.router, prefix=API)
app.include_router(play.router, prefix=API)
app.include_router(admin.router, prefix=API)

app.mount("/uploads", StaticFiles(directory=str(settings.upload_path)), name="uploads")
app.mount(
    "/h5test",
    StaticFiles(directory=str(Path(__file__).parent / "static" / "h5test"), html=True),
    name="h5test",
)


@app.get("/admin")
async def admin_page():
    return FileResponse(Path(__file__).parent / "static" / "admin.html")


@app.get("/health")
async def health():
    return {"ok": True}

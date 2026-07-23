import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ["GEOGAME_DB_URL"] = "sqlite+aiosqlite:///./test_geogame.db"
os.environ["GEOGAME_UPLOAD_DIR"] = "./test_uploads"
os.environ["GEOGAME_ADMIN_TOKEN"] = "test-admin"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

for f in pathlib.Path(".").glob("test_geogame.db*"):
    f.unlink()

from app.db import async_session_maker, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.geo import seed_regions  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await init_db()
    async with async_session_maker() as session:
        await seed_regions(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

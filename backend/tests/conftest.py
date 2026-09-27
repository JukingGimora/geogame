import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ["GEOGAME_DB_URL"] = "sqlite+aiosqlite:///./test_geogame.db"
os.environ["GEOGAME_UPLOAD_DIR"] = "./test_uploads"
os.environ["GEOGAME_ADMIN_TOKEN"] = "test-admin"
# 测试不许碰真的 AI 接口。Settings 现在会读 backend/.env(tools/ 下的脚本需要),
# 于是线上的 key 会被测试捡起来:跑一次测试就真的去调模型,又慢又花钱。
# 环境变量优先级高于 .env,所以在这里清掉就够了
os.environ["GEOGAME_AI_API_KEY"] = ""
os.environ["GEOGAME_AI_BASE_URL"] = ""
os.environ["GEOGAME_FAKE_AI"] = "true"
# 同理:.env 里有 OSS 的账号,不清掉的话测试会把图片真的传到生产的对象存储上,
# 而且本地断言"文件落在 ./test_uploads"会全部找不到文件
os.environ["GEOGAME_OSS_BUCKET"] = ""
os.environ["GEOGAME_OSS_ACCESS_KEY_ID"] = ""
os.environ["GEOGAME_OSS_ACCESS_KEY_SECRET"] = ""
os.environ["GEOGAME_OSS_ENDPOINT"] = ""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

for f in pathlib.Path(".").glob("test_geogame.db*"):
    f.unlink()

from app.db import async_session_maker, init_db  # noqa: E402
from app.services import ratelimit  # noqa: E402
from app.main import app  # noqa: E402
from app.services.geo import seed_regions  # noqa: E402


@pytest_asyncio.fixture
async def client():
    # 限速是按 IP 数的,整套测试在同一个"IP"上跑,跑到第 60 次上传就 429。
    # 每个用例开始前清一次计数:限速逻辑本身照样被执行到,只是不跨用例累加
    ratelimit._hits.clear()
    await init_db()
    async with async_session_maker() as session:
        await seed_regions(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

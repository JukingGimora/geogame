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

from sqlalchemy import delete  # noqa: E402

from app.db import Base, async_session_maker, init_db  # noqa: E402
from app.services import ratelimit  # noqa: E402
from app.main import app  # noqa: E402
from app.services.geo import seed_regions  # noqa: E402


@pytest_asyncio.fixture
async def client():
    """每个用例都从一个空库开始。

    原来所有用例共用一个库,于是"别的用例的玩家猜了我的照片"这种事会随机
    把断言顶掉——pytest 每次跑的顺序还不一样,同一份代码时红时绿。
    与其一处处把断言放宽成"大于等于",不如让每个用例真的互不相干:
    断言能写成确切的数字,failing 的时候也指得准。
    """
    # 限速按 IP 数,整套测试在同一个"IP"上跑,到第 60 次上传就 429
    ratelimit._hits.clear()
    await init_db()
    async with async_session_maker() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(delete(table))
        await session.commit()
        await seed_regions(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

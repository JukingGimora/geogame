from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.db_url, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


if settings.db_url.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        """SQLite 的默认设置跟"一个网站 + 偶尔跑个批量脚本"是冲突的。

        默认的 journal_mode=delete 下,**读事务会挡住写事务**:
        批量翻译脚本在那儿慢慢读,线上就插不进一个新用户,`/auth/guest` 直接 500,
        等于整站登不上。实际踩过一次。

        WAL 让读和写各走各的,读多少都不挡写;busy_timeout 让偶发的抢锁
        等五秒再说,而不是立刻抛 "database is locked"。
        """
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


async def get_session():
    async with async_session_maker() as session:
        yield session


async def init_db():
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.db_url.startswith("sqlite"):
            # 上面那个 connect 钩子只作用于新连接,已经存在的库文件还得显式转一次。
            # WAL 是写进文件头的,转一次就一直是
            await conn.execute(text("PRAGMA journal_mode=WAL"))

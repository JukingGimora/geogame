import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
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


def _prefers_chinese(accept_language: str) -> bool:
    """浏览器说它想读什么语言。

    `Accept-Language` 长这样:`zh-CN,zh;q=0.9,en;q=0.8`,按 q 值排优先级,
    不写 q 就是 1。取最高的那个看是不是中文。

    用它而不是 IP 或时区,是因为要判断的是"他读什么",不是"他人在哪":
    在巴黎的中国人该看中文,新加坡人该看英文(那儿也是 UTC+8),
    在上海的法国人该看英文——这三种情况 IP 和时区各只能对一个。
    顺带还省掉了"收集位置信息"这件要声明的事。
    """
    best_zh, best_other = -1.0, -1.0
    for part in accept_language.split(","):
        tag, _, params = part.strip().partition(";")
        if not tag or tag == "*":
            continue
        q = 1.0
        if params.strip().startswith("q="):
            try:
                q = float(params.strip()[2:])
            except ValueError:
                q = 1.0
        if tag.lower().startswith("zh"):
            best_zh = max(best_zh, q)
        else:
            best_other = max(best_other, q)
    return best_zh >= best_other and best_zh >= 0


@app.get("/")
async def web_root(request: Request):
    """对外只发这一个链接,按浏览器自己报的语言分流。

    他手动切过语言的话,前端会写一个 cookie,这里优先认它——
    否则他每次点收藏夹都要被送回系统语言那一边,切了等于白切。
    """
    picked = request.cookies.get("geogame_lang")
    if picked not in ("zh", "en"):
        picked = "zh" if _prefers_chinese(request.headers.get("accept-language", "")) else "en"
    return RedirectResponse(f"/{picked}/", status_code=302)


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

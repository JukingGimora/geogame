"""今天踩过的坑,一条一条钉下来。

这里每个用例都对应一个真出过问题的地方,不是为了凑覆盖率:
改坏了会让人重打三关、让删掉的照片把页面打成 500、让英文站冒中文。
"""
import pytest
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.db import async_session_maker
from app.models import Photo, Round, Run
from tests.test_game_flow import login, upload_and_approve


async def seed_photos(client, uploader, n, lat=20.0, lng=100.0):
    """铺开一点:同一局里两张照片不能挨得太近(16km 内)。"""
    return [await upload_and_approve(client, uploader, lat + i * 0.4, lng + i * 0.4, f"故事{i}")
            for i in range(n)]


async def play_round(client, player, run, guess=(0.0, 0.0)):
    rd = next(x for x in run["rounds"] if not x["finished"])
    r = await client.post(f"/api/v1/rounds/{rd['round_id']}/guess", headers=player,
                          json={"lat": guess[0], "lng": guess[1]})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_roam_resumes_instead_of_restarting(client):
    """走过两关的人再进漫游,只补最后一关。

    原来「引导走完没有」按人算(历史累计三关),发关卡却每次都发三关,
    两套规则各说各的:他打完第 1 关就被判定成老用户,剩下 2 关白打。
    """
    up = await login(client, "rule-roam-up")
    me = await login(client, "rule-roam-me")
    await seed_photos(client, up, 6, 20.0, 100.0)

    run = (await client.post("/api/v1/runs", headers=me, json={"mode": "roam"})).json()
    assert len(run["rounds"]) == 3 and run["total_rounds"] == 3

    for _ in range(2):
        run = (await client.get(f"/api/v1/runs/{run['run_id']}", headers=me)).json()
        await play_round(client, me, run)

    assert (await client.get("/api/v1/auth/me", headers=me)).json()["roam_done"] is False

    # 中途跑去开了认真局,上一局漫游被收尾
    await client.post("/api/v1/runs", headers=me, json={"mode": "serious"})
    again = (await client.post("/api/v1/runs", headers=me, json={"mode": "roam"})).json()
    assert len(again["rounds"]) == 1, "走过两关,只该再发一关"
    assert again["streak"] == 2 and again["total_rounds"] == 3

    await play_round(client, me, again)
    assert (await client.get("/api/v1/auth/me", headers=me)).json()["roam_done"] is True

    # 引导走完就收起来,不能靠它绕过每天三条命
    r = await client.post("/api/v1/runs", headers=me, json={"mode": "roam"})
    assert r.status_code == 409 and r.json()["detail"] == "roam_over"


@pytest.mark.asyncio
async def test_three_misses_end_the_day(client):
    """命按人按天算。猜歪三次当天就不能再开认真局了。"""
    up = await login(client, "rule-lives-up")
    me = await login(client, "rule-lives-me")
    await seed_photos(client, up, 8, 40.0, 10.0)

    run = (await client.post("/api/v1/runs", headers=me, json={})).json()
    for _ in range(3):
        run = (await client.get(f"/api/v1/runs/{run['run_id']}", headers=me)).json()
        res = await play_round(client, me, run, guess=(-40.0, -160.0))   # 地球对面,必然掉命
    assert res["lives_left"] == 0 and res["ended"] == "lives"

    r = await client.post("/api/v1/runs", headers=me, json={})
    assert r.status_code == 409 and r.json()["detail"] == "no_lives"


@pytest.mark.asyncio
async def test_deleted_photo_does_not_break_the_run(client):
    """照片被删了,引用它的那一关不能把页面打成 500。

    线上有 44 个这样的关卡(早年删测试图留下的),29 局至今挂着 playing:
    续上那一局就会对着不存在的照片取文件名,谁点「开始」谁 500。
    """
    up = await login(client, "rule-orphan-up")
    me = await login(client, "rule-orphan-me")
    await seed_photos(client, up, 4, -10.0, 30.0)

    run = (await client.post("/api/v1/runs", headers=me, json={})).json()
    run_id = run["run_id"]
    # 测试之间共用一个库,这一局未必发的是刚传的那几张,按实际发到的删
    keys = [r["photo_url"].rsplit("/", 1)[-1] for r in run["rounds"]]

    # 绕过接口直接删:接口本来就不许删已经被人玩过的照片,这里要造的正是那个坏状态
    async with async_session_maker() as s:
        await s.execute(sa_delete(Photo).where(Photo.file_key.in_(keys)))
        await s.commit()

    r = await client.get(f"/api/v1/runs/{run_id}", headers=me)
    assert r.status_code == 200, r.text
    assert r.json()["rounds"] == [], "照片没了的关应该被跳过,不是崩"


@pytest.mark.asyncio
async def test_cannot_delete_a_photo_people_played(client):
    """删了会让别人的成绩指向一张不存在的图,所以不许删。

    不去打一局再删:测试之间共用一个库,这一局发到的未必是他自己那几张。
    直接给照片接一条关卡记录,要测的就是"有人玩过"这个状态本身。
    """
    up = await login(client, "rule-del-up")
    me = await login(client, "rule-del-me")
    ids = await seed_photos(client, up, 2, 55.0, 60.0)

    r = await client.delete(f"/api/v1/photos/{ids[0]}", headers=up)
    assert r.status_code == 200, "没人玩过的照片该能删"

    async with async_session_maker() as s:
        run = Run(user_id=1, mode="serious", status="playing")
        s.add(run)
        await s.flush()
        s.add(Round(run_id=run.id, photo_id=ids[1], order_index=0))
        await s.commit()

    r = await client.delete(f"/api/v1/photos/{ids[1]}", headers=up)
    assert r.status_code == 409 and r.json()["detail"] == "photo_already_played"
    assert me


@pytest.mark.asyncio
async def test_account_deletion_leaves_nothing(client):
    """平台要求能自己删光,而且要真的删光——旧 token 必须立刻失效。"""
    up = await login(client, "rule-gone-up")
    gone = await login(client, "rule-gone-me")
    await seed_photos(client, up, 3, 5.0, 5.0)

    run = (await client.post("/api/v1/runs", headers=gone, json={})).json()
    await play_round(client, gone, run)
    await client.post("/api/v1/feedback", headers=gone, json={"content": "注销前留一条"})

    r = await client.delete("/api/v1/auth/account", headers=gone)
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert (await client.get("/api/v1/auth/me", headers=gone)).status_code == 401


@pytest.mark.asyncio
async def test_english_site_gets_english(client):
    """X-Lang: en 的请求,后端给的中文要换成英文。

    文化圈的**名字**故意还是中文:它同时是配色表的键和开局回传的 chapter,
    换掉的那一刻配色全丢、开局参数也对不上。只有描述换语言。
    """
    up = await login(client, "rule-lang-up")
    en = await login(client, "rule-lang-en", lang="en")
    await seed_photos(client, up, 3, 35.0, 105.0)

    circles = (await client.get("/api/v1/circles", headers=en)).json()
    east = next(c for c in circles["items"] if c["name"] == "东亚")
    assert east["name"] == "东亚", "圈名是键,不能翻"
    assert east["desc"].isascii(), f"英文站的描述还是中文: {east['desc']}"

    run = (await client.post("/api/v1/runs", headers=en, json={})).json()
    rid = run["rounds"][0]["round_id"]
    for level in (3, 4):
        h = (await client.post(f"/api/v1/rounds/{rid}/hints", headers=en, json={"level": level})).json()
        # 发到哪个国家的照片是随机的,所以只断言"没有中文"
        assert h["content"].isascii(), f"提示{level} 不是英文: {h['content']}"

    # 从英文站进来的新账号拿英文名字:榜上一排汉字,外语用户一个也认不出
    who = (await client.get("/api/v1/auth/me", headers=en)).json()
    assert who["nickname"].isascii(), f"英文站的随机昵称还是中文: {who['nickname']}"


@pytest.mark.asyncio
async def test_chinese_site_stays_chinese(client):
    """小程序和中文站不能被英文改动带跑。"""
    up = await login(client, "rule-lang-zh-up")
    zh = await login(client, "rule-lang-zh")
    await seed_photos(client, up, 3, 36.0, 106.0)

    circles = (await client.get("/api/v1/circles", headers=zh)).json()
    east = next(c for c in circles["items"] if c["name"] == "东亚")
    assert not east["desc"].isascii()

    run = (await client.post("/api/v1/runs", headers=zh, json={})).json()
    rid = run["rounds"][0]["round_id"]
    h = (await client.post(f"/api/v1/rounds/{rid}/hints", headers=zh, json={"level": 3})).json()
    assert h["content"].startswith("在")


@pytest.mark.asyncio
async def test_root_sends_you_to_your_own_language(client):
    """对外只发一个链接,按浏览器自己报的语言分流。

    用 Accept-Language 而不是 IP 或时区:要判断的是"他读什么"不是"他人在哪"。
    新加坡也是 UTC+8,时区分不出来;在巴黎的中国人该看中文,IP 分不出来。
    """
    cases = [
        ("zh-CN,zh;q=0.9,en;q=0.8", "/zh/"),
        ("en-US,en;q=0.9", "/en/"),
        ("en-SG,en;q=0.9,zh-CN;q=0.5", "/en/"),   # 新加坡,时区跟中国一样
        ("fr-FR,fr;q=0.9,en;q=0.8", "/en/"),      # 在上海的法国人
        ("en;q=0.8,zh-CN;q=0.9", "/zh/"),         # q 值倒着写
        ("", "/en/"),
    ]
    for header, target in cases:
        r = await client.get("/", headers={"Accept-Language": header}, follow_redirects=False)
        assert r.status_code == 302, r.text
        assert r.headers["location"] == target, f"{header!r} 应该去 {target}"

    # 他手动切过语言就认他的,别再按系统语言把他送回去
    r = await client.get(
        "/",
        headers={"Accept-Language": "en-US,en;q=0.9", "Cookie": "geogame_lang=zh"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/zh/"


@pytest.mark.asyncio
async def test_english_story_shows_up_in_chinese(client):
    """上传者用英文写的故事,中文站要看到中文。

    翻译方向按原文定,不是固定中译英。原来写死"中文原文→英文译文",
    等第一个英文上传者出现,中文玩家的提示①和揭晓页就会是英文原文裸奔。
    """
    from app.models import Hint
    from app.services.translate import detect_lang, other, put

    up = await login(client, "rule-en-story-up")
    zh = await login(client, "rule-en-story-zh")
    ids = await seed_photos(client, up, 3, 48.0, 2.0)

    # 造一张英文故事的照片,并按"缺哪边补哪边"的方向存一条中文译文
    async with async_session_maker() as s:
        photo = await s.get(Photo, ids[0])
        photo.story = "A quiet morning by the harbour, the ferries had not started yet."
        assert detect_lang(photo.story) == "en"
        assert other(detect_lang(photo.story)) == "zh", "英文原文该补的是中文"
        # 提示①跟 photo.story 是同一段话,审核时一起写的,这里也一起改
        h1 = await s.scalar(select(Hint).where(Hint.photo_id == photo.id, Hint.level == 1))
        h1.content = photo.story
        await put(s, photo.id, "story", "港口边安静的清晨,渡轮还没开班。", "manual", "zh")
        await s.commit()

    # 中文站拿到中文
    r = await client.post("/api/v1/runs", headers=zh, json={"photo_id": ids[0]})
    rid = next(x["round_id"] for x in r.json()["rounds"])
    h = (await client.post(f"/api/v1/rounds/{rid}/hints", headers=zh, json={"level": 1})).json()
    assert h["content"] == "港口边安静的清晨,渡轮还没开班。", h

    # 英文站直接拿原文,不该去找一条不存在的"英译英"
    en = await login(client, "rule-en-story-en", lang="en")
    r = await client.post("/api/v1/runs", headers=en, json={"photo_id": ids[0]})
    rid = next(x["round_id"] for x in r.json()["rounds"])
    h = (await client.post(f"/api/v1/rounds/{rid}/hints", headers=en, json={"level": 1})).json()
    assert h["content"].startswith("A quiet morning"), h


@pytest.mark.asyncio
async def test_chinese_story_still_shows_up_in_english(client):
    """反方向别改坏了:中文故事在英文站还是要看到英文。"""
    from app.models import Hint
    from app.services.translate import put

    up = await login(client, "rule-zh-story-up")
    en = await login(client, "rule-zh-story-en", lang="en")
    ids = await seed_photos(client, up, 3, -33.0, 151.0)

    async with async_session_maker() as s:
        photo = await s.get(Photo, ids[0])
        photo.story = "那天的海边很安静,渡轮还没开班。"
        h1 = await s.scalar(select(Hint).where(Hint.photo_id == photo.id, Hint.level == 1))
        h1.content = photo.story
        await put(s, photo.id, "story", "A quiet morning by the sea.", "manual", "en")
        await s.commit()

    r = await client.post("/api/v1/runs", headers=en, json={"photo_id": ids[0]})
    rid = next(x["round_id"] for x in r.json()["rounds"])
    h = (await client.post(f"/api/v1/rounds/{rid}/hints", headers=en, json={"level": 1})).json()
    assert h["content"] == "A quiet morning by the sea.", h

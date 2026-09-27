"""一局游戏从头走到尾。

这套测试在 2026-07-30 到 09-27 之间一直是挂的:查重、`/photos/mine` 换成
`{items, summary}`、提示④从省份改成国家+方位、认真局不再固定五关——
功能改了没人改测试,于是它两个月没拦住过任何东西。现在断言的是当下的行为。
"""
import io
import random
import uuid

import pytest
from PIL import Image

ADMIN = {"X-Admin-Token": "test-admin"}


def jpeg_bytes(seed: int | None = None) -> bytes:
    """每张图都得不一样:上传接口按转码后的 sha256 查重,重复的图会被 409 挡掉。

    两条坑:
    - 只改一个像素不够。JPEG 是有损的,单像素的差别会被压回去,转码后还是同一个哈希
    - 不能靠测试自己数数。测试之间共用一个数据库,顺序一变就可能撞上,
      于是"改了上传逻辑"和"测试自己撞车了"分不开。直接用随机噪点,不留侥幸
    """
    rnd = random.Random(seed) if seed is not None else random.Random(uuid.uuid4().int)
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 150), (120, 140, 90))
    for x in range(40):
        for y in range(40):
            img.putpixel((x, y), (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
    img.save(buf, "JPEG")
    return buf.getvalue()


async def login(client, device_key, lang: str = "zh"):
    r = await client.post(
        "/api/v1/auth/guest", json={"device_key": device_key}, headers={"X-Lang": lang}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "X-Lang": lang}


async def upload_and_approve(client, headers, lat, lng, story):
    r = await client.post(
        "/api/v1/photos",
        headers=headers,
        files={"file": ("t.jpg", jpeg_bytes(), "image/jpeg")},
        data={"lat": lat, "lng": lng, "story": story},
    )
    assert r.status_code == 200, r.text
    photo_id = r.json()["id"]
    r = await client.post(f"/api/v1/admin/photos/{photo_id}/approve", headers=ADMIN)
    assert r.status_code == 200, r.text
    return photo_id


@pytest.mark.asyncio
async def test_full_game_flow(client):
    uploader = await login(client, "device-uploader-001")
    player = await login(client, "device-player-002")

    # 同一局里两张照片不能挨得太近(16km 内),所以铺开一点
    for i in range(5):
        await upload_and_approve(client, uploader, 30.65 + i * 0.3, 104.08 + i * 0.3, f"川西的第{i}段记忆")

    r = await client.post("/api/v1/runs", headers=player, json={})
    assert r.status_code == 200, r.text
    run = r.json()
    # 认真局不再是固定五关:先备两关,打完一关补一关,三条命掉光才结束
    assert run["mode"] == "serious"
    assert len(run["rounds"]) == 2
    round_id = run["rounds"][0]["round_id"]

    r = await client.post(f"/api/v1/rounds/{round_id}/hints", headers=player, json={"level": 4})
    assert r.status_code == 200, r.text
    # 提示④现在是「国家·方位」,不再是省份
    assert r.json()["content"].startswith("在中国·")

    r = await client.post(f"/api/v1/rounds/{round_id}/guess", headers=player, json={"lat": 30.66, "lng": 104.09})
    assert r.status_code == 200, r.text
    result = r.json()
    assert 0 < result["score"] <= 2000  # 用了④级提示,四折封顶
    assert "记忆" in result["story"]
    assert result["ai"] is not None and "reasoning" in result["ai"]
    assert result["country"] == "中国"

    # 同一关不能猜第二次
    r = await client.post(f"/api/v1/rounds/{round_id}/guess", headers=player, json={"lat": 30, "lng": 104})
    assert r.status_code == 409

    # 「被看见」数的是有多少个**不同的人**猜过我的照片,不是猜了几次
    r = await client.get("/api/v1/auth/me", headers=uploader)
    assert r.json()["points"] == 1


@pytest.mark.asyncio
async def test_own_photos_are_never_served_to_you(client):
    """自己的照片不会发给自己——知道答案等于白送满分,也会把「被看见」刷成假的。

    库里只剩他自己传的图时,开不出局,而且要能说清是哪一种空:
    「你都玩过了」和「库里只剩你自己的」对玩家是两回事,提示也不一样。
    """
    solo = await login(client, "device-solo-003")
    for i in range(3):
        await upload_and_approve(client, solo, 25.04 + i * 0.3, 102.71 + i * 0.3, f"云南故事{i}")

    r = await client.post("/api/v1/runs", headers=solo, json={})
    assert r.status_code == 409
    assert r.json()["detail"] == "only_own_photos"

    r = await client.get("/api/v1/auth/me", headers=solo)
    assert r.json()["points"] == 0


@pytest.mark.asyncio
async def test_moderation_gate(client):
    uploader = await login(client, "device-mod-004")
    r = await client.post(
        "/api/v1/photos",
        headers=uploader,
        files={"file": ("t.jpg", jpeg_bytes(), "image/jpeg")},
        data={"lat": 39.9, "lng": 116.4, "story": "待审核"},
    )
    photo_id = r.json()["id"]
    r = await client.get("/api/v1/admin/photos?status=pending", headers=ADMIN)
    assert any(p["id"] == photo_id for p in r.json()["items"])
    r = await client.post(f"/api/v1/admin/photos/{photo_id}/reject", headers=ADMIN, json={"reason": "画质过低"})
    assert r.json()["status"] == "rejected"
    r = await client.get("/api/v1/photos/mine", headers=uploader)
    mine = [p for p in r.json()["items"] if p["id"] == photo_id][0]
    assert mine["status"] == "rejected" and mine["reject_reason"] == "画质过低"


@pytest.mark.asyncio
async def test_admin_requires_token(client):
    r = await client.get("/api/v1/admin/photos")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_heic_upload_converted_to_jpeg(client):
    import pillow_heif

    pillow_heif.register_heif_opener()
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (90, 120, 160)).save(buf, format="HEIF")
    headers = await login(client, "device-heic-005")
    r = await client.post(
        "/api/v1/photos",
        headers=headers,
        files={"file": ("iphone.heic", buf.getvalue(), "image/heic")},
        data={"lat": 29.65, "lng": 91.14, "story": "HEIC"},
    )
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/photos/mine", headers=headers)
    assert r.json()["items"][0]["url"].endswith(".jpg")


@pytest.mark.asyncio
async def test_leaderboard(client):
    uploader = await login(client, "device-rank-up")
    player = await login(client, "device-rank-pl")
    for i in range(4):
        await upload_and_approve(client, uploader, 34.34 + i * 0.3, 108.94 + i * 0.3, f"长安故事{i}")

    # 榜单看的是**打完的**局,所以要一路打到这一局结束(猜得准就不掉命,打空题库为止)
    r = await client.post("/api/v1/runs", headers=player, json={})
    run_id = r.json()["run_id"]
    for _ in range(12):
        run = (await client.get(f"/api/v1/runs/{run_id}", headers=player)).json()
        todo = [x for x in run["rounds"] if not x["finished"]]
        if run["status"] != "playing" or not todo:
            break
        for rd in todo:
            await client.post(f"/api/v1/rounds/{rd['round_id']}/guess", headers=player,
                              json={"lat": 34.34, "lng": 108.94})
    assert run["status"] == "finished"

    r = await client.get("/api/v1/leaderboard?board=best_run", headers=player)
    body = r.json()
    assert body["me"]["rank"] == 1 and body["top"][0]["is_me"]
    # 「被看见」= 有几个不同的人猜过我的照片。一个玩家打几关都只算一个人
    r = await client.get("/api/v1/leaderboard?board=points", headers=uploader)
    assert r.json()["me"]["value"] == 1


@pytest.mark.asyncio
async def test_feedback_flow(client):
    headers = await login(client, "device-fb-001")
    r = await client.post("/api/v1/feedback", headers=headers, json={"content": "希望增加夜景主题", "contact": "wx:abc"})
    assert r.status_code == 200
    fid = r.json()["id"]
    r = await client.get("/api/v1/admin/feedback?status=open", headers=ADMIN)
    assert any(f["id"] == fid and "夜景" in f["content"] for f in r.json())
    r = await client.post(f"/api/v1/admin/feedback/{fid}/close", headers=ADMIN)
    assert r.json()["status"] == "closed"

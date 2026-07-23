import io

import pytest
from PIL import Image

ADMIN = {"X-Admin-Token": "test-admin"}


def jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 150), (120, 140, 90)).save(buf, "JPEG")
    return buf.getvalue()


async def login(client, device_key):
    r = await client.post("/api/v1/auth/guest", json={"device_key": device_key})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


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

    for i in range(5):
        await upload_and_approve(client, uploader, 30.65 + i * 0.1, 104.08 + i * 0.1, f"川西的第{i}段记忆,那天雨下得很大")

    r = await client.post("/api/v1/runs", headers=player, json={})
    assert r.status_code == 200, r.text
    run = r.json()
    assert len(run["rounds"]) == 5
    round_id = run["rounds"][0]["round_id"]

    r = await client.post(f"/api/v1/rounds/{round_id}/hints", headers=player, json={"level": 4})
    assert r.status_code == 200, r.text
    assert "在四川" in r.json()["content"]

    r = await client.post(f"/api/v1/rounds/{round_id}/guess", headers=player, json={"lat": 30.66, "lng": 104.09})
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["distance_km"] < 80  # 5张种子照片彼此相距约55km内,抽中任意一张都应命中此范围
    assert 0 < result["score"] <= 2000  # 用了④级提示,四折封顶
    assert "记忆" in result["story"]
    assert result["ai"] is not None and "reasoning" in result["ai"]
    assert result["truth"]["lat"] == pytest.approx(30.85, abs=0.5)

    r = await client.post(f"/api/v1/rounds/{round_id}/guess", headers=player, json={"lat": 30, "lng": 104})
    assert r.status_code == 409

    r = await client.get("/api/v1/auth/me", headers=uploader)
    assert r.json()["points"] == 2  # 被玩+1,被猜中(≤100km)+1


@pytest.mark.asyncio
async def test_self_guess_earns_no_points(client):
    solo = await login(client, "device-solo-003")
    for i in range(5):
        await upload_and_approve(client, solo, 25.04, 102.71 + i * 0.05, f"云南故事{i}")
    r = await client.post("/api/v1/runs", headers=solo, json={})
    round_id = r.json()["rounds"][0]["round_id"]
    await client.post(f"/api/v1/rounds/{round_id}/guess", headers=solo, json={"lat": 25.04, "lng": 102.71})
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
    assert any(p["id"] == photo_id for p in r.json())
    r = await client.post(f"/api/v1/admin/photos/{photo_id}/reject", headers=ADMIN, json={"reason": "画质过低"})
    assert r.json()["status"] == "rejected"
    r = await client.get("/api/v1/photos/mine", headers=uploader)
    mine = [p for p in r.json() if p["id"] == photo_id][0]
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
    assert r.json()[0]["url"].endswith(".jpg")


@pytest.mark.asyncio
async def test_leaderboard(client):
    uploader = await login(client, "device-rank-up")
    player = await login(client, "device-rank-pl")
    for i in range(5):
        await upload_and_approve(client, uploader, 34.34 + i * 0.05, 108.94, f"长安故事{i}")
    r = await client.get("/api/v1/regions?level=province", headers=player)
    shaanxi = [x for x in r.json() if x["name"] == "陕西"][0]
    r = await client.post("/api/v1/runs", headers=player, json={"region_id": shaanxi["id"]})
    for rd in r.json()["rounds"]:
        await client.post(f"/api/v1/rounds/{rd['round_id']}/guess", headers=player, json={"lat": 34.34, "lng": 108.94})
    r = await client.get("/api/v1/leaderboard?board=best_run", headers=player)
    body = r.json()
    assert body["me"]["rank"] == 1 and body["me"]["value"] > 20000
    assert body["top"][0]["is_me"]
    r = await client.get("/api/v1/leaderboard?board=points", headers=uploader)
    body = r.json()
    assert body["me"]["value"] == 10  # 5张图各被玩+1、被猜中+1


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

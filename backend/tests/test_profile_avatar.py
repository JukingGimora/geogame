"""改昵称/头像会不会同步,以及榜单上到底发了什么。"""
import pytest

from tests.test_game_flow import login, upload_and_approve


@pytest.mark.asyncio
async def test_profile_sync(client):
    guest_res = await client.post(
        "/api/v1/auth/guest",
        json={"device_key": "avatar-test-device", "nickname": "游客", "avatar_url": "https://cdn.example.com/old.png"},
    )
    assert guest_res.status_code == 200
    headers = {"Authorization": f"Bearer {guest_res.json()['token']}"}

    profile_res = await client.post(
        "/api/v1/auth/profile",
        headers=headers,
        json={"nickname": "小明", "avatar_url": "https://cdn.example.com/new.png"},
    )
    assert profile_res.status_code == 200
    assert profile_res.json()["avatar_url"] == "https://cdn.example.com/new.png"

    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["nickname"] == "小明"
    assert me_res.json()["avatar_url"] == "https://cdn.example.com/new.png"


@pytest.mark.asyncio
async def test_leaderboard_sends_nickname_not_avatar(client):
    """榜单只发昵称。

    头像现在是前端按昵称当场画的像素图(components/PixelAvatar.vue),
    榜单再发一个 URL 没人用。原来这里往 points_ledger 插一行就指望上榜——
    那是旧口径,现在「被看见」数的是有几个不同的人猜过你的照片。
    """
    uploader = await login(client, "device-lb-avatar-up")
    player = await login(client, "device-lb-avatar-pl")
    await client.post(
        "/api/v1/auth/profile", headers=uploader,
        json={"nickname": "上榜的人", "avatar_url": "https://cdn.example.com/x.png"},
    )
    for i in range(2):
        await upload_and_approve(client, uploader, 22.5 + i * 0.4, 114.0 + i * 0.4, f"故事{i}")

    run = (await client.post("/api/v1/runs", headers=player, json={})).json()
    for rd in run["rounds"]:
        await client.post(f"/api/v1/rounds/{rd['round_id']}/guess", headers=player,
                          json={"lat": 22.5, "lng": 114.0})

    data = (await client.get("/api/v1/leaderboard?board=points", headers=uploader)).json()
    mine = [r for r in data["top"] if r["is_me"]]
    assert mine, f"传了图又被人猜过,不该不在榜上: {data}"
    assert mine[0]["nickname"] == "上榜的人"
    assert "avatar_url" not in mine[0]

import pytest

from app.db import async_session_maker
from app.models import PointsLedger


@pytest.mark.asyncio
async def test_profile_sync_and_leaderboard_avatar(client):
    guest_res = await client.post(
        "/api/v1/auth/guest",
        json={"device_key": "avatar-test-device", "nickname": "游客", "avatar_url": "https://cdn.example.com/old.png"},
    )
    assert guest_res.status_code == 200
    token = guest_res.json()["token"]

    headers = {"Authorization": f"Bearer {token}"}
    profile_res = await client.post(
        "/api/v1/auth/profile",
        headers=headers,
        json={"nickname": "小明", "avatar_url": "https://cdn.example.com/new.png"},
    )
    assert profile_res.status_code == 200
    assert profile_res.json()["avatar_url"] == "https://cdn.example.com/new.png"

    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["avatar_url"] == "https://cdn.example.com/new.png"

    async with async_session_maker() as session:
        session.add(PointsLedger(user_id=me_res.json()["id"], delta=100, kind="test"))
        await session.commit()

    leaderboard_res = await client.get("/api/v1/leaderboard?board=points", headers=headers)
    assert leaderboard_res.status_code == 200
    data = leaderboard_res.json()
    assert data["top"][0]["avatar_url"] == "https://cdn.example.com/new.png"

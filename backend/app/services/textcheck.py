"""昵称的内容安全检查。

昵称是公开展示的——它会出现在排行榜和别人的揭晓页上。平台把这类位置
当作"用户生成内容"来查,出了问题是小程序被处理,不是那个人被处理。

两层:
1. 本地规则,所有人都过一遍——长度、控制字符、留联系方式、明显的违禁词。
   不联网,微信接口挂了也还在。
2. 微信的 msgSecCheck,只有小程序用户过得了(它认 openid)。H5 用户只有第一层,
   这是接口本身的限制,不是偷懒。

哪层都不确定的时候放行:昵称不是发言,错杀的代价比漏放大。
"""
import re
import time

import httpx

from app.config import settings

MAX_LEN = 16

# 留联系方式的各种写法。旅行游戏里加微信引流是最常见的一种,
# 平台把它算作"诱导添加",查到一次就是整个小程序的事
CONTACT = re.compile(
    r"(微信|weixin|薇信|v信|加我|qq群|telegram|whatsapp"
    r"|[wv]x\s*[:：号]?\s*\d{4}"  # wx12345、vx:8888 这类直接把号写在名字里的
    r"|\+?\d{11})",
    re.IGNORECASE,
)

# 明显过不了的几类。不求全——全的那份在微信手里,这里只挡最扎眼的,
# 以及 H5 用户(微信接口对他们不可用)最容易撞上的
BANNED = (
    "习近平", "法轮功", "六四", "台独", "藏独", "疆独",
    "操你", "fuck", "婊子", "鸡巴",
    "招嫖", "约炮", "裸聊", "博彩", "赌球", "代开发票",
    "客服", "官方", "管理员", "系统消息",
)

_token: tuple[str, float] | None = None


def local_reason(name: str) -> str | None:
    """本地那一层。返回错误码(前端翻成人话),通过则返回 None。"""
    text = name.strip()
    if not text:
        return "nickname_empty"
    if len(text) > MAX_LEN:
        return "nickname_too_long"
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        return "nickname_bad_chars"
    low = text.lower()
    if any(w in low for w in BANNED):
        return "nickname_banned"
    if CONTACT.search(text):
        return "nickname_contact"
    return None


async def _access_token() -> str | None:
    """小程序的接口调用凭证,自己缓存。微信那边两小时过期,提前五分钟换。"""
    global _token
    if not settings.wechat_appid or not settings.wechat_secret:
        return None
    if _token and _token[1] > time.time():
        return _token[0]
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": settings.wechat_appid,
                    "secret": settings.wechat_secret,
                },
            )
        data = r.json()
    except httpx.HTTPError:
        return None
    if "access_token" not in data:
        return None
    _token = (data["access_token"], time.time() + max(600, data.get("expires_in", 7200) - 300))
    return _token[0]


async def wechat_reason(name: str, openid: str) -> str | None:
    """微信那一层。查不通就返回 None 放行——接口抖一下不该让人改不了名字。"""
    token = await _access_token()
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.post(
                "https://api.weixin.qq.com/wxa/msg_sec_check",
                params={"access_token": token},
                json={"content": name, "version": 2, "scene": 1, "openid": openid},
            )
        data = r.json()
    except httpx.HTTPError:
        return None
    # 87014 是老版本的"命中违规";新版本看 result.suggest
    if data.get("errcode") == 87014 or data.get("result", {}).get("suggest") in ("risky", "review"):
        return "nickname_rejected"
    return None


async def nickname_reason(name: str, openid: str | None) -> str | None:
    reason = local_reason(name)
    if reason or not openid:
        return reason
    return await wechat_reason(name, openid)

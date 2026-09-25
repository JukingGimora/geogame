"""AI 对手。FAKE_AI=true 走开发桩;false 走真实视觉模型(OpenAI兼容接口)。

判分与提示③④永远不走这里(幻觉隔离,见 scoring.py 头注)。
AI挂了/解析失败就不生成 ai_guesses 记录,不影响游戏本身(architecture.md 第1条)。
"""
import base64
import json
import random
import re

import httpx

from app.config import settings
from app.models import AIGuess, Photo
from app.services.scoring import haversine_km, score_from_distance
from app.storage import storage

CANNED_REASONING = (
    "我注意到画面中的植被与光线特征,结合建筑风格与道路样式,"
    "推测拍摄地在{name}一带。置信度{conf}%。(开发桩:正式版由视觉模型生成)"
)

AI_PROMPT = (
    "你在玩一个看图猜中国地点的游戏。仔细观察这张照片里的线索"
    "(植被、建筑风格、路牌、车牌、地形、气候特征等),先用中文写一段第一人称推理独白"
    "(比如\"我注意到...,推测...\",3到5句,可以大胆但要基于画面细节),然后给出你最终猜测的坐标。"
    "只输出一个JSON对象,不要有任何多余文字或markdown代码块标记,格式:"
    '{"reasoning": "推理独白文本", "lat": 纬度小数, "lng": 经度小数, "confidence": 0到100的整数}'
)

HINT_PROMPT = (
    "你在玩一个看图猜地点的游戏,这是给玩家的一条付费提示,不是最终答案。"
    "仔细观察这张照片,只描述你注意到的一个具体视觉线索"
    "(比如某种植被、建筑风格、地形样式、气候特征等),用中文写1到2句话,语气像善意提醒。"
    "严禁:提到任何国家、省份、城市、景点或建筑的名称;"
    "严禁念出照片里出现的文字——牌匾、石碑、路牌、招牌、横幅上的字一个都不许引用或转述;"
    "严禁说出这是哪座具体的塔、寺、桥、遗址或纪念馆;严禁给坐标或下结论。"
    "直接输出这句话本身,不要有多余的引号、前缀或解释。"
)

RETRY_SUFFIX = (
    "上一次你违规了:请重新只写视觉观察,"
    "不要出现任何专有名称,不要引用画面里的任何文字,不要使用引号。"
)

# 模型偶尔还是会把石碑上的字念出来(线上真出现过"马跃檀溪遗址"),等于直接报答案。
# 所以生成完再过一道:带引号的专名、省名国名一律判漏,宁可退回兜底文案。
_QUOTE_CHARS = "「」『』“”\"《》"


def _leaks_answer(text: str) -> bool:
    if any(ch in text for ch in _QUOTE_CHARS):
        return True
    from app.services.circles import COUNTRIES
    from app.services.geo import PROVINCE_ADCODE

    names = set(PROVINCE_ADCODE) | {c[0] for c in COUNTRIES}
    return any(name in text for name in names if len(name) >= 2)


async def fake_ai_guess(photo: Photo) -> AIGuess:
    offset_km = random.uniform(30, 600)
    bearing = random.uniform(0, 6.28)
    dlat = (offset_km / 111.0) * random.uniform(0.3, 1.0) * (1 if bearing < 3.14 else -1)
    dlng = (offset_km / 95.0) * random.uniform(0.3, 1.0) * (1 if bearing % 3.14 < 1.57 else -1)
    lat, lng = photo.lat + dlat, photo.lng + dlng
    distance = haversine_km(photo.lat, photo.lng, lat, lng)
    guess = AIGuess(
        photo_id=photo.id,
        lat=lat,
        lng=lng,
        distance_km=round(distance, 2),
        score=score_from_distance(distance),
        reasoning=CANNED_REASONING.format(name="该区域", conf=random.randint(55, 90)),
        model="fake-ai-v0",
    )
    return guess


def _image_url(photo: Photo) -> str:
    url = storage.url(photo.file_key)
    if url.startswith("http"):
        return url
    data = (settings.upload_path / photo.file_key).read_bytes()
    return f"data:image/jpeg;base64,{base64.b64encode(data).decode()}"


async def real_ai_guess(photo: Photo) -> AIGuess | None:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.ai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai_api_key}"},
                json={
                    "model": settings.ai_model,
                    # qwen3.7 系列默认先思考:慢到 25-60 秒、会超时,还会把 AI 对手推得更强
                    "enable_thinking": False,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": AI_PROMPT},
                                {"type": "image_url", "image_url": {"url": _image_url(photo)}},
                            ],
                        }
                    ],
                },
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError):
        return None

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        lat, lng = float(parsed["lat"]), float(parsed["lng"])
        reasoning = str(parsed["reasoning"])
        confidence = int(parsed.get("confidence", 60))
    except (KeyError, ValueError, TypeError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None

    distance = haversine_km(photo.lat, photo.lng, lat, lng)
    guess = AIGuess(
        photo_id=photo.id,
        lat=lat,
        lng=lng,
        distance_km=round(distance, 2),
        score=score_from_distance(distance),
        reasoning=f"{reasoning}置信度{confidence}%。",
        model=settings.ai_model,
    )
    return guess


async def real_ai_hint(photo: Photo) -> str | None:
    """提示②专用的单独调用——只要一条软性观察线索,不能像 real_ai_guess 那样带坐标/结论(会变相剧透)。

    漏了答案就重问一次:模型多半只是没把"别念照片里的字"当回事,
    第二次带上更硬的措辞通常就收敛了,一次调用还不到一分钱。
    """
    for attempt in range(2):
        prompt = HINT_PROMPT if attempt == 0 else HINT_PROMPT + RETRY_SUFFIX
        text = await _ask_hint(photo, prompt)
        if text and not _leaks_answer(text):
            return text[:255]
    return None


async def _ask_hint(photo: Photo, prompt: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.ai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai_api_key}"},
                json={
                    "model": settings.ai_model,
                    "enable_thinking": False,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": _image_url(photo)}},
                            ],
                        }
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError):
        return None

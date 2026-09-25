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
from app.services.cities import find_city
from app.services.scoring import haversine_km, score_from_distance
from app.storage import storage

CANNED_REASONING = (
    "我注意到画面中的植被与光线特征,结合建筑风格与道路样式,"
    "推测拍摄地在{name}一带。置信度{conf}%。(开发桩:正式版由视觉模型生成)"
)

# 早期题库全是中国照片,提示词就写死了"猜中国地点"。后来照片走向全世界,
# 模型被这句话逼着往中国猜:布哈拉的宣礼塔它认得出来,却仍给了个新疆的坐标,差 1300 公里。
# AI 出两套东西,按时间分开:
#   猜之前 —— HINT_PROMPT,只说"该从哪几个角度看",严禁任何地名(见下面);
#   猜完之后 —— 这里,亮出它的答案和推理,地名该说就说。
# 之前一版把两者混成一个"不准提地名"的提示词,等于把 AI 这个亮点也废了。
AI_PROMPT = (
    "你在玩一个看图猜地点的游戏,照片可能来自世界上任何一个国家。"
    "这段话是在玩家已经猜完之后才给他看的,所以要说出你的结论。"
    "用中文写2到3句:第一句直接说你认为这是哪里,"
    "后面用一两句说清楚是靠哪一两处特征认出来的。"
    "不要复述所有细节,不要写置信度,不要客套。"
    "另外单独给出 city 字段,用当地常用的英文拼写(如 Bukhara、Tbilisi、Xi\'an),"
    "我们用它来定位坐标——你给的经纬度只作参考。"
    "只输出一个JSON对象,不要有任何多余文字或markdown代码块标记,格式:"
    '{"reasoning": "推理文本", "city": "英文城市名", "lat": 纬度小数, "lng": 经度小数, '
    '"confidence": 0到100的整数}'
)

HINT_PROMPT = (
    "你在陪玩家猜这张照片拍在哪。你的任务不是告诉他答案,而是示范**你会怎么推**。"
    "挑出画面里两三处最能说明问题的特征,每处一句说清它能缩到多大范围,"
    "最后一句说这几处交起来剩下什么样的地方。"
    "**全文不超过80个汉字**,每句话都要有信息量,不要铺垫、不要形容词堆砌、不要感叹词。"
    "例如:\"屋顶是筒瓦,东亚传统建筑常见;墙体却是夯土,说明更干旱;"
    "院里那几棵杨树,把范围压到了北方的干旱地带。\""
    "严禁:提到任何国家、省份、城市、景点、建筑的名字;"
    "严禁念出或转述画面里的任何文字;严禁说出最终结论。"
    "直接输出这段话本身,不要有多余的引号、前缀或解释。"
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
    """AI 的推理归玩家看,城市和坐标归审核用。

    分开是有原因的:玩家要的是"这张照片该往哪儿看"的思路,不是答案;
    而我们核对上传者有没有标错坐标,需要的恰恰是最准的那个点。
    """
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
        # 模型说得出"布哈拉",却给了个新疆的坐标:地名它记得住,经纬度是编的。
        # 所以地名归它,坐标查我们自己的城市表,它给的坐标只用来消歧同名城市。
        city = str(parsed.get("city", "")).strip()
        if city:
            found = find_city(city, near=(lat, lng))
            if found:
                lat, lng = found
        # 模型说得出"布哈拉",却给了个新疆的坐标——地名它记得住,经纬度是编的。
        # 所以地名归它,坐标归我们自己的城市表,它给的坐标只用来消歧同名城市。
        city = str(parsed.get("city", "")).strip()
        if city:
            found = find_city(city, near=(lat, lng))
            if found:
                lat, lng = found
        reasoning = re.sub(r"[。.]?\s*置信度[^。]*。?\s*$", "。", str(parsed["reasoning"])).strip()
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
        reasoning=reasoning,
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

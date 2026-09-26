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
from app.services.cities import country_center, find_city
from app.services.scoring import haversine_km, score_from_distance
from app.storage import storage

CANNED_REASONING = (
    "我注意到画面中的植被与光线特征,结合建筑风格与道路样式,"
    "推测拍摄地在{name}一带。置信度{conf}%。(开发桩:正式版由视觉模型生成)"
)

# AI 出两套东西,按时间分开给玩家:
#   猜之前 —— clue,只说"该从哪几个角度看",严禁任何地名;
#   猜完之后 —— reasoning,亮出它的答案和依据,地名该说就说。
# 但两套必须是**同一次看图**的产物。以前分两次调用,同一张毛里求斯唐人街,
# 线索说"南洋华人聚落",答案说"拉包尔"——玩家照着线索推,推到的地方跟 AI 自己的结论都对不上。
READ_PROMPT = (
    "你在玩一个看图猜地点的游戏,照片可能来自世界上任何一个国家。"
    "看一遍这张照片,一次给出两样东西。\n"
    "\n"
    "一、clue:玩家猜之前看的,示范**你会怎么推**,不是告诉他答案。"
    "挑出画面里两三处最能说明问题的特征,每处一句说清它能缩到多大范围,"
    "最后一句说这几处交起来剩下什么样的地方。"
    "全文不超过80个汉字,每句都要有信息量,不要铺垫、不要形容词堆砌、不要感叹词。"
    "例如:\"屋顶铺筒瓦,是用汉字那一带的老做法;墙体却是夯土,说明比沿海干旱得多;"
    "院里那几棵杨树,把范围又往北压了一截。\"\n"
    "clue 里严禁出现任何专有名称——国家、省份、城市、地区、王朝、民族、品牌、景点、建筑都算。"
    "下面这些都是违规的写法:\"指向苏瓦的商业区\"、\"旁遮普或德里宫廷特色\"、"
    "\"莫卧儿帝国核心区域\"、\"南亚次大陆\"、\"非洲南部城市\"、\"红色帐篷是Vodafone标志\"。"
    "该怎么写:把名字换成它代表的那类地方——"
    "\"指向热带岛国的港口老街\"、\"典型的南亚宫廷工艺\"改成\"繁复的象牙镶嵌工艺,"
    "属于某个历史上擅长此道的宫廷传统\"、\"某国际电信品牌的广告\"。"
    "也严禁念出或转述画面里的任何文字(招牌、路牌、广告词都不行),严禁说出最终结论。\n"
    "\n"
    "二、reasoning:玩家猜完之后才看的,所以要说出你的结论。"
    "用中文写2到3句:第一句直接说你认为这是哪里,"
    "后面用一两句说清楚是靠哪一两处特征认出来的。"
    "不要复述所有细节,不要写置信度,不要客套。\n"
    "\n"
    "clue 和 reasoning 必须指向同一个判断:clue 里推出来的方向,"
    "要正好是 reasoning 认定的那个地方,只是 clue 不点破名字。\n"
    "\n"
    "另外给 city 字段,用当地常用的英文拼写(如 Bukhara、Tbilisi、Xi\'an),"
    "以及 country 字段,两位 ISO 国家代码(毛里求斯 MU、巴布亚新几内亚 PG、乌兹别克斯坦 UZ)。"
    "city 必须就是 reasoning 第一句里说的那个地方,不要换成附近更有名的城市;"
    "我们用这两个字段定位坐标,你给的经纬度只作参考。\n"
    "\n"
    "只输出一个JSON对象,不要有任何多余文字或markdown代码块标记,格式:"
    '{"clue": "推理示范", "reasoning": "结论与依据", "city": "英文城市名", '
    '"country": "两位国家代码", "lat": 纬度小数, "lng": 经度小数, "confidence": 0到100的整数}'
)

RETRY_SUFFIX = (
    "上一次 clue 违规了:请重写 clue,只写视觉观察,"
    "不要出现任何专有名称,不要引用画面里的任何文字,不要使用引号。reasoning 照常写。"
)

# 模型偶尔还是会把石碑上的字念出来(线上真出现过"马跃檀溪遗址"),等于直接报答案。
# 所以生成完再过一道:带引号的专名、省名国名一律判漏,宁可退回兜底文案。
_QUOTE_CHARS = "「」『』“”\"《》"


# 文化圈的名字等于把提示③白送出去,也算泄底
_REGION_WORDS = (
    "东亚", "东南亚", "南亚", "伊斯兰", "西欧", "东欧", "非洲", "拉美", "太平洋",
    "次大陆", "中东", "北美", "南美", "中亚", "西亚", "北非", "东非", "西非", "南非",
)


def _leaks_answer(text: str) -> bool:
    if any(ch in text for ch in _QUOTE_CHARS):
        return True
    if any(w in text for w in _REGION_WORDS):
        return True
    # 拉丁字母连成一串,多半是招牌上的字或者品牌名被念出来了
    if re.search(r"[A-Za-z]{3,}", text):
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



async def real_ai_read(photo: Photo) -> tuple[str | None, AIGuess | None]:
    """看一次图,同时拿到猜前的线索和猜后的答案。

    以前是两次调用,各看各的图,结果线索和答案能指向两个地方——玩家照着线索推,
    推出来的跟 AI 自己的结论对不上。一次调用出两样东西,它们至少来自同一个判断。

    线索泄底就整个重问一次(措辞更硬),不到一分钱的事。
    """
    for attempt in range(2):
        prompt = READ_PROMPT if attempt == 0 else READ_PROMPT + RETRY_SUFFIX
        parsed = await _ask(photo, prompt)
        if not parsed:
            return None, None
        clue = str(parsed.get("clue", "")).strip()
        guess = _to_guess(photo, parsed)
        if clue and not _leaks_answer(clue):
            return clue[:255], guess
        # 线索不合格但答案还能用:最后一轮就只丢线索,别把答案一起扔了
        if attempt == 1:
            return None, guess
    return None, None


def _to_guess(photo: Photo, parsed: dict) -> AIGuess | None:
    try:
        lat, lng = float(parsed["lat"]), float(parsed["lng"])
        # 模型说得出"布哈拉",却给了个新疆的坐标:地名它记得住,经纬度是编的。
        # 所以地名归它,坐标查我们自己的城市表,它给的坐标只用来消歧同名城市。
        # 国家代码一定要用上:不然它嘴上说毛里求斯,针能插到阿曼去,
        # 玩家看到的就是一段自相矛盾的话——那是我们的毛病,不是它猜错了。
        city = str(parsed.get("city", "")).strip()
        cc = str(parsed.get("country", "")).strip()[:2].upper()
        found = find_city(city, near=(lat, lng), cc=cc or None) if city else None
        if not found and cc:
            found = country_center(cc)
        if found:
            lat, lng = found
        reasoning = re.sub(r"[。.]?\s*置信度[^。]*。?\s*$", "。", str(parsed["reasoning"])).strip()
    except (KeyError, ValueError, TypeError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None

    distance = haversine_km(photo.lat, photo.lng, lat, lng)
    return AIGuess(
        photo_id=photo.id,
        lat=lat,
        lng=lng,
        distance_km=round(distance, 2),
        score=score_from_distance(distance),
        reasoning=reasoning,
        # 它自己说的是哪儿。跟针的落点分开存:对不上的时候,审核页要能一眼看出
        # 是"它猜错了"还是"我们把它的答案搬错了地方"
        place=", ".join(x for x in (city, cc) if x)[:64],
        model=settings.ai_model,
    )


async def _ask(photo: Photo, prompt: str) -> dict | None:
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
                                {"type": "text", "text": prompt},
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
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

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
from app.services.cities import country_fallback, find_city, nearest_cc
from app.services.scoring import haversine_km, score_from_distance
from app.storage import storage

CANNED_REASONING = (
    "我注意到画面中的植被与光线特征,结合建筑风格与道路样式,"
    "推测拍摄地在{name}一带。置信度{conf}%。(开发桩:正式版由视觉模型生成)"
)

# AI 出两套东西,按时间分开给玩家:
#   猜之前 —— clue,只说"该从哪几个角度看",严禁任何地名;
#   猜完之后 —— reasoning,亮出它的答案和依据,地名该说就说。
#
# 两次调用,但**不是各看各的**:先认地方,再把认出来的结论交给第二次调用,
# 让它照着这个结论倒推线索。这样线索和答案在构造上就不可能打架。
# (试过合成一次调用出两样:线索确实一致了,可中位误差从 15km 掉到 24km——
#  同一套提示词重跑 20 张有 19 张一字不差,所以那是真亏,不是模型在抖。)
# 这段一个字都别改:它就是合并之前中位误差 15km 的那版。
# 我加过"具体到城市或地标"和"不要换成附近更有名的城市",结果西安从 0.1km 变成 1216km。
ANSWER_PROMPT = (
    "你在玩一个看图猜地点的游戏,照片可能来自世界上任何一个国家。"
    "这段话是在玩家已经猜完之后才给他看的,所以要说出你的结论。"
    "用中文写2到3句:第一句直接说你认为这是哪里,"
    "后面用一两句说清楚是靠哪一两处特征认出来的。"
    "不要复述所有细节,不要写置信度,不要客套。"
    "另外单独给出 city 字段,用当地常用的英文拼写(如 Bukhara、Tbilisi、Xi\'an),"
    "以及 country 字段,两位 ISO 国家代码(毛里求斯 MU、巴布亚新几内亚 PG、乌兹别克斯坦 UZ)。"
    "我们用这两个字段定位坐标——你给的经纬度只作参考,但国家代码必须和你上面说的结论一致。"
    "只输出一个JSON对象,不要有任何多余文字或markdown代码块标记,格式:"
    '{"reasoning": "推理文本", "city": "英文城市名", "country": "两位国家代码", '
    '"lat": 纬度小数, "lng": 经度小数, "confidence": 0到100的整数}'
)

CLUE_PROMPT = (
    "你刚看过这张照片,并且已经认定它拍摄于:{answer}\n"
    "\n"
    "现在回到玩家猜之前。写一条线索,示范**你是怎么推到这个结论的**,但一个字都不能点破。"
    "挑出画面里两三处最能说明问题的特征,每处一句说清它能把范围缩到多小。"
    "最后一句只描述这几处交起来剩下的是**什么样的地方**——说它的样子、气候、生计、历史处境,"
    "绝不能说它叫什么,连大区名都不行。"
    "全文不超过80个汉字,每句都要有信息量,不要铺垫、不要形容词堆砌、不要感叹词。"
    "例如:\"屋顶铺筒瓦,是用汉字那一带的老做法;墙体却是夯土,说明比沿海干旱得多;"
    "院里那几棵杨树,把范围又往北压了一截。\"\n"
    "严禁出现任何专有名称。以下这些**全都违规**,它们是真实出现过的错误:\n"
    "  \"指向苏瓦的商业区\"、\"旁遮普或德里宫廷特色\"、\"莫卧儿帝国核心区域\"——点了城市/王朝的名字;\n"
    "  \"指向南太平洋岛国的印裔聚居区\"、\"东南亚某处历史贸易港口\"、\"中亚某正在发展的首都\"、"
    "\"仅见于东亚文化圈\"、\"南亚老城典型基建\"——**大区名也是名字**,东亚/东南亚/南亚/中亚/"
    "西欧/东欧/拉美/太平洋/非洲/中东/北美/南美这些词一个都不能出现;\n"
    "  \"中国西北某历史文化名城\"、\"位于中华人民共和国境内\"——国名更不行;\n"
    "  \"红色帐篷上的Vodafone标志\"、\"招牌写着永華昌\"——念出了画面里的字或品牌。\n"
    "同样的意思该这么写:\"一座靠海、华人做了几代生意的山城老街\"、"
    "\"殖民者修的红砖教堂,配着热带港口的旧广场\"、\"石头砌的老楼和裹着绿网的新楼挤在一起,"
    "是个正在翻新的内陆首府\"、\"帐篷上是某国际电信品牌的圆环标\"。\n"
    "也严禁念出或转述画面里的任何文字(招牌、路牌、广告词、说明牌都不行),严禁说出最终结论。\n"
    "\n"
    "再给一个 keyword:**最后一条线索**,两到六个字,说出这地方\"是个什么\"。"
    "要的是通名,不是专名——\"盐湖\"、\"关隘\"、\"唐人街\"、\"赛马场\"、\"火山口\"、\"石窟\"、"
    "\"铁路枢纽\"、\"高山牧场\"都合格;\"察尔汗\"、\"剑门关\"、\"布罗莫\"不合格,那是名字。"
    "它是玩家花最多代价才买的一条,所以要挑最能缩小范围的那个通名,"
    "别给\"风景\"、\"城市\"、\"海边\"这种放之四海而皆准的词。\n"
    "\n"
    "只输出一个JSON对象,不要有任何多余文字或markdown代码块标记,格式:"
    '{"clue": "推理示范", "keyword": "通名"}'
)

# 重问时把上次栽在哪一条告诉它。泛泛说"你违规了"它改不准,
# 指名道姓说"你写了『南亚』"基本一次就收敛
RETRY_SUFFIX = (
    "\n\n上一次你写的线索违规了,原因是:{reason}。"
    "请重写,把那个词换成对这类地方的描述,别再出现任何专有名称、画面里的文字或引号。"
)

# 模型偶尔还是会把石碑上的字念出来(线上真出现过"马跃檀溪遗址"),等于直接报答案。
# 所以生成完再过一道:带引号的专名、省名国名一律判漏,宁可退回兜底文案。
_QUOTE_CHARS = "「」『』“”\"《》"


# 文化圈的名字等于把提示③白送出去,也算泄底
_REGION_WORDS = (
    "东亚", "东南亚", "南亚", "伊斯兰", "西欧", "东欧", "非洲", "拉美", "太平洋",
    "次大陆", "中东", "北美", "南美", "中亚", "西亚", "北非", "东非", "西非", "南非",
)


def leak_reason(text: str) -> str | None:
    """线索哪里泄了底。返回具体原因,给调参时看;没泄就返回 None。"""
    hit = next((ch for ch in _QUOTE_CHARS if ch in text), None)
    if hit:
        return f"引号 {hit}(多半在念画面里的字)"
    hit = next((w for w in _REGION_WORDS if w in text), None)
    if hit:
        return f"大区名 {hit}(等于白送提示③)"
    # 拉丁字母连成一串,多半是招牌上的字或者品牌名被念出来了
    m = re.search(r"[A-Za-z]{3,}", text)
    if m:
        return f"拉丁字母 {m.group(0)}"
    from app.services.circles import COUNTRIES
    from app.services.geo import PROVINCE_ADCODE

    names = set(PROVINCE_ADCODE) | {c[0] for c in COUNTRIES}
    hit = next((n for n in names if len(n) >= 2 and n in text), None)
    return f"地名 {hit}" if hit else None


def _leaks_answer(text: str) -> bool:
    return leak_reason(text) is not None


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



async def real_ai_read(photo: Photo) -> tuple[str | None, str | None, AIGuess | None]:
    """先认地方,再让它照着这个结论倒推线索和关键词。返回 (线索, 关键词, 猜测)。

    第二步把第一步的结论原样喂回去,所以线索说的方向必然通向答案认定的那个地方——
    一致性是构造出来的,不靠模型自觉。

    线索泄底只重问线索那一步,答案不用再认一遍。
    """
    parsed = await _ask(photo, ANSWER_PROMPT)
    if not parsed:
        return None, None, None
    guess = _to_guess(photo, parsed)
    if not guess:
        return None, None, None

    answer = f"{guess.place}。{guess.reasoning}"
    prompt = CLUE_PROMPT.format(answer=answer)
    keyword = None
    for _ in range(2):
        second = await _ask(photo, prompt)
        if not second:
            break
        clue = str(second.get("clue", "")).strip()
        word = str(second.get("keyword", "")).strip()
        # 关键词单独判:线索不合格不该连累它,它自己泄底也不该连累线索
        if word and not leak_reason(word):
            keyword = word[:16]
        why = leak_reason(clue) if clue else "没给线索"
        if not why:
            return clue[:255], keyword, guess
        prompt = CLUE_PROMPT.format(answer=answer) + RETRY_SUFFIX.format(reason=why)
    # 两次都泄底:答案还能用,线索退回兜底文案,别把整张图的结果一起扔了
    return None, keyword, guess


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
            # 城市表里没有它说的那个地方——景点、小岛、村子本来就不是城市。
            # 这时它自己给的坐标只要落在它说的国家里,就用它的:
            # 针插在它说的那个东西上,才跟它那句话对得上。
            # 落到别的国家去了才兜底,那说明坐标是编的(布哈拉给成新疆就是这种)。
            found = (lat, lng) if nearest_cc(lat, lng) == cc else country_fallback(cc, near=(lat, lng))
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


async def _ask(photo: Photo, prompt: str, as_json: bool = True):
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
    if not as_json:
        return text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

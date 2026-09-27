"""把故事(提示①)和 AI 线索(提示②)翻成英文。

H5 是给外语用户看的,但这两条是内容不是模板:故事是上传者自己写的,线索是模型写的,
只能预先翻好存进 hint_translations。提示③④(国家、方位)不在这里——那两条是程序拼的,
读的时候现算(见 api/play.py 的 _hint_en)。

审核通过时顺手翻,不然每通过一张照片,英文版上那一关就多一条中文——
这个洞会自己长大,而且要等外语用户来告诉你才发现。
批量补历史存量用 tools/translate_hints.py,它跟这里共用同一段 prompt 和同一套检查:
两边各写一份的话,总有一天会只改其中一份。
"""
import asyncio
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AIGuess, Hint, Photo, PhotoText
from app.services.i18n import COUNTRY_EN, DEMONYM_EN, SOURCE_ALIAS

logger = logging.getLogger(__name__)

LANGS = ("zh", "en")

# 要翻的三段内容。story 同时供提示①和揭晓页用
# (实测 220/220 两处是同一段文字,没必要翻两遍)
FIELDS = ("story", "clue", "reasoning")

_CJK = range(0x4E00, 0x9FFF + 1)


def detect_lang(text: str) -> str:
    """这段话是哪种语言写的。

    只分中英两种,有汉字就算中文。判得糙没关系:用途是决定"往哪边翻",
    而一段话里只要出现汉字,英文读者就需要一份译文。

    上传者可以用英文写故事,所以原文不一定是中文——
    固定按"中译英"翻的话,英文故事会被拿去做一次英译英(白花钱),
    而中文站那边一行译文都没有,中文玩家看到的是英文原文。
    """
    return "zh" if any(ord(ch) in _CJK for ch in text) else "en"


def other(lang: str) -> str:
    return "en" if lang == "zh" else "zh"

# 忠实翻译,不是改写。多说一个字、少说一个字都会改变这一关的难度
_RULES = (
    "1. Never add a place name, region, country or landmark that is not already in the source. "
    "If the source is vague about where it is, the translation must be exactly as vague.\n"
    "   In particular: when the source gives only a direction or a relative region and does NOT "
    "name the country, your translation must not name it either. "
    "Translate 北方某超大城市 as 'a megacity in the north', never 'a megacity in northern China'. "
    "Naming the country is a separate, more expensive hint in this game — "
    "leaking it here hands the player the answer at a discount.\n"
    "2. Keep hedged wording hedged. 'looks like', 'probably', 'could be' stay uncertain; "
    "never turn a guess into a statement.\n"
    "3. Keep the register: a traveller's own note stays personal and plain; "
    "reasoning notes stay matter-of-fact.\n"
    "4. Output the translation only. No quotes, no notes, no romanisation of words "
    "the reader does not need.\n"
)

_INTO = {
    "en": "You translate text from a photo-location guessing game into natural English.\n",
    "zh": "You translate text from a photo-location guessing game into natural Chinese.\n",
}


def system_prompt(target: str) -> str:
    return _INTO[target] + "Rules, in order of importance:\n" + _RULES


def payload(model: str, text: str, target: str = "en") -> dict:
    """两种模型两种形状。

    qwen-mt-* 是专用翻译模型,**不收 system 角色**(实测直接 400:
    Role must be in [user, assistant]),约束只能塞进它自己的 translation_options.domains。
    通用模型走正常的 system + user;qwen3 系是思考模型,一条 87 字的句子会烧掉两千多个
    思考 token,所以关掉思考——翻译不需要它想。
    """
    if model.startswith("qwen-mt"):
        return {
            "model": model,
            "messages": [{"role": "user", "content": text}],
            "translation_options": {
                "source_lang": "Chinese" if target == "en" else "English",
                "target_lang": "English" if target == "en" else "Chinese",
                "domains": system_prompt(target),
            },
        }
    return {
        "model": model,
        "temperature": 0,
        "enable_thinking": False,
        "messages": [
            {"role": "system", "content": system_prompt(target)},
            {"role": "user", "content": text},
        ],
    }


def leaked(zh: str, en: str) -> str | None:
    """译文点了原文没点的国家吗。

    实测过:中文只说"北方某超大城市",模型译成 "a megacity in northern China" ——
    国家是提示③,单独收四成分。线索②里泄出来,等于把答案打折卖了。
    自动查一遍比人眼翻四百条可靠。
    """
    low = en.lower()
    for zh_name, en_name in COUNTRY_EN.items():
        # 原文点过就不算泄露。"华人""汉字""沙俄"这些也算点过,见 SOURCE_ALIAS
        if any(a in zh for a in SOURCE_ALIAS.get(zh_name, (zh_name,))):
            continue
        for word in (en_name, *DEMONYM_EN.get(zh_name, ())):
            w = word.lower()
            i = low.find(w)
            if i < 0:
                continue
            # 整词匹配:China 不该被 Chinatown 之类误伤
            before = low[i - 1] if i else " "
            after = low[i + len(w)] if i + len(w) < len(low) else " "
            if not before.isalpha() and not after.isalpha():
                return word
    return None


async def translate_text(
    client: httpx.AsyncClient, model: str, text: str, target: str = "en"
) -> str:
    r = await client.post(
        f"{settings.ai_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.ai_api_key}"},
        json=payload(model, text, target),
        timeout=90,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


async def source_texts(session: AsyncSession, photo_id: int) -> dict[str, str]:
    """这张照片待翻的三段中文原文。取不到的那段就不在返回里。"""
    photo = await session.get(Photo, photo_id)
    clue = await session.scalar(
        select(Hint.content).where(Hint.photo_id == photo_id, Hint.level == 2)
    )
    reasoning = await session.scalar(
        select(AIGuess.reasoning).where(AIGuess.photo_id == photo_id)
    )
    out = {"story": photo.story if photo else "", "clue": clue or "", "reasoning": reasoning or ""}
    return {k: v for k, v in out.items() if v}


async def translate_photo(session: AsyncSession, photo_id: int, model: str | None = None) -> int:
    """把这张照片的故事、AI线索、AI推理翻到**缺的那一种语言**,返回成功几条。

    方向按原文定,不是固定中译英:故事是上传者自己写的,可能本来就是英文,
    那要补的是中文译文。AI 线索和推理永远是我们的 prompt 产出的中文,
    所以它们实际上总是中译英——但走的是同一段逻辑,将来换 prompt 语言也不用改这里。

    **翻不出来不算审核失败。** 阿里的内容审核会拦下一些完全正常的句子
    (实测「仿民国时期的电影街区」就被判 data_inspection_failed),
    没配 AI 的环境更是一条都翻不了。两种情况都只记一行日志:
    没有译文时英文版照原样显示中文,一关也不会缺提示。
    """
    if not settings.ai_api_key or not settings.ai_base_url:
        return 0
    model = model or settings.translate_model
    # (字段, 原文, 要翻成哪种语言)
    todo = [(f, zh, other(detect_lang(zh))) for f, zh in (await source_texts(session, photo_id)).items()]
    if not todo:
        return 0

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(translate_text(client, model, src, target) for _, src, target in todo),
            return_exceptions=True,
        )

    ok = 0
    for (field, src, target), out in zip(todo, results):
        if isinstance(out, BaseException) or not out:
            logger.warning("translate photo %s %s->%s failed: %r", photo_id, field, target, out)
            continue
        # 推理是揭晓之后才给的,点名地点本来就是它的职责,不查泄露
        if field != "reasoning" and (leak := leaked(src, out)):
            # 泄露了就干脆不存:玩家看到原文,比看到一条送分的线索好
            logger.warning("translate photo %s %s leaked %r, 丢弃这条译文", photo_id, field, leak)
            continue
        await put(session, photo_id, field, out, model, target)
        ok += 1
    return ok


async def put(
    session: AsyncSession, photo_id: int, field: str, text: str, model: str, lang: str = "en"
) -> None:
    """写一条译文,有就覆盖。"""
    old = await session.scalar(
        select(PhotoText).where(
            PhotoText.photo_id == photo_id, PhotoText.field == field, PhotoText.lang == lang
        )
    )
    # 截断就是把一句话砍在中间。宁可存长一点也不要半句话
    text = text[:4000]
    if old:
        old.content, old.model = text, model
    else:
        session.add(PhotoText(photo_id=photo_id, field=field, lang=lang, content=text, model=model))

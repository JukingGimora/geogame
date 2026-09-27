#!/usr/bin/env python3
"""把故事(提示①)和 AI 线索(提示②)翻成英文,存进 hint_translations。

H5 是给外语用户看的,但这两条是内容不是模板:故事是上传者自己写的,线索是模型写的,
只能预先翻好存下来。提示③④(国家、方位)不在这里——那两条是程序拼的,读的时候现算。

  python3 tools/translate_hints.py --dry-run              # 只看要翻多少、花多少
  python3 tools/translate_hints.py --limit 5              # 先翻五张,人眼看一遍
  python3 tools/translate_hints.py --model qwen-mt-plus   # 换模型
  python3 tools/translate_hints.py --redo                 # 连已经翻过的一起重翻

**翻译要忠实,不能改信息量。** 故事里本来不点地名,译文也不能点;线索本来是"看起来像"
的口气,译文不能写成断言。这两件事都会让这一关直接送分,所以 prompt 里写死了。

已经翻过的默认跳过,可以分批跑、随时中断。
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import async_session_maker  # noqa: E402
from app.models import Hint, HintTranslation, Photo  # noqa: E402
from app.services.i18n import COUNTRY_EN  # noqa: E402

LEVELS = (1, 2)
LANG = "en"

# 忠实翻译,不是改写。多说一个字、少说一个字都会改变这一关的难度
SYSTEM = (
    "You translate Chinese text from a photo-location guessing game into natural English.\n"
    "Rules, in order of importance:\n"
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
    "4. Output the translation only. No quotes, no notes, no romanisation of Chinese words "
    "the reader does not need.\n"
)


def _payload(model: str, text: str) -> dict:
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
                "source_lang": "Chinese",
                "target_lang": "English",
                "domains": SYSTEM,
            },
        }
    return {
        "model": model,
        "temperature": 0,
        "enable_thinking": False,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": text},
        ],
    }


async def translate(client: httpx.AsyncClient, model: str, text: str) -> str:
    r = await client.post(
        f"{settings.ai_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.ai_api_key}"},
        json=_payload(model, text),
        timeout=90,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _leaked(zh: str, en: str) -> str | None:
    """译文点了原文没点的国家吗。

    实测过:中文只说"北方某超大城市",模型译成 "a megacity in northern China" ——
    国家是提示③,单独收四成分。线索②里泄出来,等于把答案打折卖了。
    自动查一遍比人眼翻四百条可靠。
    """
    low = en.lower()
    for zh_name, en_name in COUNTRY_EN.items():
        # 原文提了就不算泄露
        if zh_name in zh:
            continue
        # 整词匹配:China 不该被 Chinatown 之类误伤,也别被 Chinese 带出来
        for word in (en_name.lower(), en_name.lower() + "ese", en_name.lower() + "n"):
            i = low.find(word)
            if i < 0:
                continue
            before = low[i - 1] if i else " "
            after = low[i + len(word)] if i + len(word) < len(low) else " "
            if not before.isalpha() and not after.isalpha():
                return en_name
    return None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("GEOGAME_TRANSLATE_MODEL", "qwen-mt-plus"))
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条,0 表示全部")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redo", action="store_true", help="已经翻过的也重翻")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()

    async with async_session_maker() as session:
        done = set()
        if not args.redo:
            done = {
                (pid, lv)
                for pid, lv in await session.execute(
                    select(HintTranslation.photo_id, HintTranslation.level).where(
                        HintTranslation.lang == LANG
                    )
                )
            }
        rows = (
            await session.execute(
                select(Hint.photo_id, Hint.level, Hint.content)
                .join(Photo, Hint.photo_id == Photo.id)
                .where(Photo.status == "live", Hint.level.in_(LEVELS))
                .order_by(Hint.photo_id, Hint.level)
            )
        ).all()
        todo = [r for r in rows if (r[0], r[1]) not in done and r[2]]
        if args.limit:
            todo = todo[: args.limit]

        chars = sum(len(c) for _, _, c in todo)
        print(f"待翻 {len(todo)} 条,共 {chars} 字,模型 {args.model}")
        print(f"  已有译文 {len(done)} 条{'(--redo 会覆盖)' if args.redo else '(跳过)'}")
        if args.dry_run or not todo:
            return 0
        if not settings.ai_api_key or not settings.ai_base_url:
            print("没配 GEOGAME_AI_API_KEY / GEOGAME_AI_BASE_URL,跑不了")
            return 1

        sem = asyncio.Semaphore(args.concurrency)
        ok = fail = 0
        leaks: list[tuple[int, int, str, str, str]] = []

        async with httpx.AsyncClient() as client:
            async def one(pid: int, lv: int, zh: str) -> None:
                nonlocal ok, fail
                async with sem:
                    try:
                        en = await translate(client, args.model, zh)
                    except Exception as e:
                        fail += 1
                        print(f"  ✗ photo {pid} 等级{lv}: {e.__class__.__name__} {e}")
                        return
                old = await session.scalar(
                    select(HintTranslation).where(
                        HintTranslation.photo_id == pid,
                        HintTranslation.level == lv,
                        HintTranslation.lang == LANG,
                    )
                )
                if old:
                    old.content, old.model = en[:600], args.model
                else:
                    session.add(
                        HintTranslation(
                            photo_id=pid, level=lv, lang=LANG, content=en[:600], model=args.model
                        )
                    )
                ok += 1
                leak = _leaked(zh, en)
                if leak:
                    leaks.append((pid, lv, leak, zh, en))
                if ok <= 6:   # 头几条打出来,方便一眼看住质量
                    print(f"  photo {pid} 等级{lv}\n    中 {zh}\n    英 {en}")

            await asyncio.gather(*(one(p, lv, c) for p, lv, c in todo))
        await session.commit()
        print(f"\n成功 {ok} 条,失败 {fail} 条")
        if leaks:
            print(f"\n★ {len(leaks)} 条译文点了原文没点的国家,人眼看一遍:")
            for pid, lv, name, zh, en in leaks:
                print(f"  photo {pid} 等级{lv} 多出了「{name}」\n    中 {zh}\n    英 {en}")
            print("  改掉 prompt 再 --redo,或者单张手改")
        return 1 if fail and not ok else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

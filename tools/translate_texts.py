#!/usr/bin/env python3
"""把照片身上的中文内容翻成英文,存进 photo_texts。

英文站要显示三段中文,都是内容不是模板:

  story      上传者写的故事(提示①和揭晓页用的是同一段)
  clue       提示②,模型给的线索
  reasoning  揭晓页 AI 的推理

提示③④(国家、方位)不在这里 —— 那两条是程序拼的,读的时候现算。

审核通过时会自动翻(services/translate.py),这个脚本是给存量和返工用的:

  python3 tools/translate_texts.py --dry-run              # 只看要翻多少
  python3 tools/translate_texts.py --limit 5              # 先五条,人眼看一遍
  python3 tools/translate_texts.py --field reasoning      # 只补某一段
  python3 tools/translate_texts.py --redo                 # 连翻过的一起重翻
  python3 tools/translate_texts.py --check-only           # 不翻,只重新查一遍泄露

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
from app.models import Photo, PhotoText  # noqa: E402
from app.services.translate import (  # noqa: E402
    FIELDS,
    LANG,
    leaked,
    put,
    source_texts,
    translate_text,
)


async def check_only(session) -> int:
    """把库里已有的译文重新过一遍泄露检查。不调模型,不花钱。

    推理不查:它是揭晓之后才给的,点名地点本来就是它的职责。
    """
    rows = (
        await session.execute(
            select(PhotoText.photo_id, PhotoText.field, PhotoText.content).where(
                PhotoText.lang == LANG, PhotoText.field != "reasoning"
            )
        )
    ).all()
    hits = []
    for pid, field, en in rows:
        src = await source_texts(session, pid)
        zh = src.get(field)
        if zh and (name := leaked(zh, en)):
            hits.append((pid, field, name, zh, en))
    print(f"查了 {len(rows)} 条译文(推理不查)")
    for pid, field, name, zh, en in hits:
        print(f"\n  photo {pid} {field} 多出了「{name}」\n    中 {zh}\n    英 {en}")
    print(f"\n可疑 {len(hits)} 条" if hits else "\n没有译文点了原文没点的国家")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("GEOGAME_TRANSLATE_MODEL", settings.translate_model))
    ap.add_argument("--field", choices=FIELDS, help="只翻某一段,默认三段都翻")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条,0 表示全部")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redo", action="store_true", help="已经翻过的也重翻")
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()

    want_fields = (args.field,) if args.field else FIELDS

    async with async_session_maker() as session:
        if args.check_only:
            return await check_only(session)

        done = set()
        if not args.redo:
            done = {
                (pid, f)
                for pid, f in await session.execute(
                    select(PhotoText.photo_id, PhotoText.field).where(PhotoText.lang == LANG)
                )
            }
        photo_ids = list(
            await session.scalars(select(Photo.id).where(Photo.status == "live").order_by(Photo.id))
        )
        todo: list[tuple[int, str, str]] = []
        for pid in photo_ids:
            for field, zh in (await source_texts(session, pid)).items():
                if field in want_fields and (pid, field) not in done:
                    todo.append((pid, field, zh))
        if args.limit:
            todo = todo[: args.limit]

        chars = sum(len(z) for _, _, z in todo)
        print(f"待翻 {len(todo)} 条,共 {chars} 字,模型 {args.model}")
        print(f"  已有译文 {len(done)} 条{'(--redo 会覆盖)' if args.redo else '(跳过)'}")
        if args.dry_run or not todo:
            return 0
        if not settings.ai_api_key or not settings.ai_base_url:
            print("没配 GEOGAME_AI_API_KEY / GEOGAME_AI_BASE_URL,跑不了")
            return 1

        sem = asyncio.Semaphore(args.concurrency)
        ok = fail = 0
        leaks: list[tuple[int, str, str, str, str]] = []

        async with httpx.AsyncClient() as client:
            async def one(pid: int, field: str, zh: str) -> None:
                nonlocal ok, fail
                async with sem:
                    try:
                        en = await translate_text(client, args.model, zh)
                    except Exception as e:
                        fail += 1
                        print(f"  ✗ photo {pid} {field}: {e.__class__.__name__} {e}")
                        return
                # 推理是揭晓之后才给的,点名地点本来就是它的职责,不查泄露
                if field != "reasoning" and (name := leaked(zh, en)):
                    leaks.append((pid, field, name, zh, en))
                await put(session, pid, field, en, args.model)
                ok += 1
                if ok <= 6:   # 头几条打出来,方便一眼看住质量
                    print(f"  photo {pid} {field}\n    中 {zh}\n    英 {en}")

            await asyncio.gather(*(one(p, f, z) for p, f, z in todo))
        await session.commit()
        print(f"\n成功 {ok} 条,失败 {fail} 条")
        if leaks:
            print(f"\n★ {len(leaks)} 条译文点了原文没点的国家,人眼看一遍:")
            for pid, field, name, zh, en in leaks:
                print(f"  photo {pid} {field} 多出了「{name}」\n    中 {zh}\n    英 {en}")
            print("  改掉 prompt 再 --redo,或者单张手改")
        return 1 if fail and not ok else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

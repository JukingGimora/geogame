"""重算 AI 对手的猜测。

改过提示词或改过坐标定位的办法之后跑它。旧结果先备份成 json,
不满意能整批退回去——这东西是要花钱的,别让一次手抖白烧一遍。

服务器上跑要先把环境带上——配置是 systemd 的 EnvironmentFile 给的,
不是 pydantic 自己读 .env,手工跑会拿到默认值(fake_ai=True、没有 OSS):

    cd backend && set -a && . ./.env && set +a && python3 ../tools/rerun_ai.py --over 800

    python3 tools/rerun_ai.py --over 800      # 只重算差得远的那些
    python3 tools/rerun_ai.py --all
    python3 tools/rerun_ai.py --ids 146,147

线索和答案现在是一次调用出来的,所以两样一起换——分开换就会重新变成"言行不一致"。
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import delete as sa_delete  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import async_session_maker  # noqa: E402
from app.models import AIGuess, Photo  # noqa: E402
from app.models import Hint  # noqa: E402
from app.services.ai_stub import real_ai_read  # noqa: E402
from app.services.enrich import HINT2_FALLBACK  # noqa: E402

CONCURRENCY = 3  # 别把模型接口打满


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--over", type=float, help="只重算当前误差超过这个公里数的")
    ap.add_argument("--ids", help="逗号分隔的照片编号")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="只看会动哪些,不真跑")
    args = ap.parse_args()
    if not (args.over or args.ids or args.all):
        ap.error("要指定 --over / --ids / --all 之一")

    async with async_session_maker() as session:
        q = select(AIGuess, Photo).join(Photo, AIGuess.photo_id == Photo.id)
        if args.over:
            q = q.where(AIGuess.distance_km > args.over)
        if args.ids:
            q = q.where(Photo.id.in_([int(i) for i in args.ids.split(",")]))
        rows = (await session.execute(q)).all()
        if not rows:
            print("没有匹配的照片")
            return

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = Path(f"ai_backup_{stamp}.json")
        backup.write_text(
            json.dumps(
                [
                    {"photo_id": g.photo_id, "lat": g.lat, "lng": g.lng,
                     "distance_km": g.distance_km, "score": g.score,
                     "reasoning": g.reasoning, "place": g.place, "model": g.model}
                    for g, _ in rows
                ],
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"{len(rows)} 张,旧结果备份在 {backup}")
        if args.dry_run:
            for g, p in rows:
                print(f"  #{p.id} {p.country} 现在差 {g.distance_km}km")
            return

        sem = asyncio.Semaphore(CONCURRENCY)
        changed = 0

        async def one(old: AIGuess, photo: Photo) -> None:
            nonlocal changed
            async with sem:
                clue, keyword, fresh = await real_ai_read(photo)
            if not fresh:
                print(f"  #{photo.id} 算失败,保留旧的")
                return
            # 线索和答案是一次算出来的,就得一起换掉,不然又变成各说各的
            hint = await session.scalar(
                select(Hint).where(Hint.photo_id == photo.id, Hint.level == 2)
            )
            if hint:
                hint.content = (clue or HINT2_FALLBACK)[:255]
            # 提示⑤(关键词)跟线索同一次算出来,一起换;给不出来就把旧的删掉
            await session.execute(sa_delete(Hint).where(Hint.photo_id == photo.id, Hint.level == 5))
            if keyword:
                session.add(Hint(photo_id=photo.id, level=5, content=keyword, source="ai"))
            arrow = "→" if fresh.distance_km < old.distance_km else "↗"
            print(f"  #{photo.id} {photo.country}: {old.distance_km}km {arrow} {fresh.distance_km}km")
            old.lat, old.lng = fresh.lat, fresh.lng
            old.distance_km, old.score = fresh.distance_km, fresh.score
            old.reasoning, old.model = fresh.reasoning, fresh.model
            old.place = fresh.place
            changed += 1

        await asyncio.gather(*(one(g, p) for g, p in rows))
        await session.commit()
        print(f"\n更新了 {changed} 张")


if __name__ == "__main__":
    asyncio.run(main())

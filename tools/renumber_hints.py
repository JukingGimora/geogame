"""把库里的提示换成新的四级阶梯。

旧的五级留下的东西:①故事前半句 ②AI线索 ③文化圈 ④国家(大国加方位) ⑤关键字(没生成过)。
新的四级:①故事整段 ②AI线索 ③国家 ④国家·方位。

所以 ①③④ 全部按当前规则重算,②(AI 线索)原样保留——那是花钱算出来的,规则没变。

    cd backend && python3 ../tools/renumber_hints.py --dry-run
    cd backend && python3 ../tools/renumber_hints.py
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import delete as sa_delete  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import async_session_maker  # noqa: E402
from app.models import Hint, Photo  # noqa: E402
from app.services.circles import coarse_area, locate  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    async with async_session_maker() as session:
        photos = (await session.scalars(select(Photo))).all()
        changed = 0
        for photo in photos:
            if not photo.country:
                photo.country, photo.circle = locate(photo.lat, photo.lng)
            area = coarse_area(photo.country, photo.lat, photo.lng)
            if args.dry_run:
                if changed < 12:
                    story = (photo.story or "")[:24]
                    print(f"  #{photo.id:<4} ①{story or '(没故事)'}  ③在{photo.country}  ④在{area}")
                changed += 1
                continue

            # ② 是花钱算出来的,规则没变,原样留着;⑤ 从来没生成过,顺手清干净
            await session.execute(
                sa_delete(Hint).where(Hint.photo_id == photo.id, Hint.level.in_((1, 3, 4, 5)))
            )
            if photo.story:
                session.add(Hint(photo_id=photo.id, level=1, content=photo.story[:255], source="uploader"))
            session.add(Hint(photo_id=photo.id, level=3, content=f"在{photo.country}", source="system"))
            session.add(Hint(photo_id=photo.id, level=4, content=f"在{area}", source="system"))
            changed += 1
        if not args.dry_run:
            await session.commit()
        print(f"\n{'会处理' if args.dry_run else '已处理'} {changed} 张")


if __name__ == "__main__":
    asyncio.run(main())

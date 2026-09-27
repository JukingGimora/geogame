#!/usr/bin/env python3
"""对一遍两份语言文件:代码用到的 key 有没有漏,两边有没有对不齐。

漏了的那一边会把 key 本身当文案显示出来(比如页面上出现 "map.noLives"),
而这种错不会让构建失败,只能靠查。加文案时顺手跑一下:

    python3 scripts/check-locale.py
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "frontend" / "src"
LOCALES = ("zh-CN", "en")


def used_keys() -> set[str]:
    keys = set()
    for f in list(SRC.rglob("*.vue")) + list(SRC.rglob("*.ts")):
        if f.parent.name == "locale":
            continue
        for m in re.finditer(r"\bt(?:List|Map)?\(\s*'([a-zA-Z0-9_.]+)'", f.read_text()):
            keys.add(m.group(1))
    return keys


def defined_keys(name: str) -> set[str]:
    """按缩进扫一遍就够了,不值得为这个引一个 TS 解析器。"""
    keys, section = set(), None
    for line in (SRC / "locale" / f"{name}.ts").read_text().splitlines():
        m = re.match(r"^  ([\w一-鿿]+): \{", line)
        if m:
            section = m.group(1)
            # 整段也能被取用:tMap('circles')、tList('play.hints') 要的是一整个对象
            keys.add(section)
            continue
        m = re.match(r"^    ([\w一-鿿]+):", line)
        if m and section:
            keys.add(f"{section}.{m.group(1)}")
    return keys


used = used_keys()
defined = {name: defined_keys(name) for name in LOCALES}
bad = 0

for name, keys in defined.items():
    missing = sorted(used - keys)
    if missing:
        bad = 1
        print(f"★ {name}.ts 缺 {len(missing)} 个代码在用的 key:")
        for k in missing:
            print(f"    {k}")

only = {name: sorted(defined[name] - defined[other])
        for name, other in zip(LOCALES, reversed(LOCALES))}
for name, keys in only.items():
    if keys:
        bad = 1
        print(f"★ 只有 {name}.ts 有,另一份没有({len(keys)} 个):")
        for k in keys:
            print(f"    {k}")

print(f"\n代码用到 {len(used)} 个 key," + "、".join(f"{n} 定义 {len(k)} 个" for n, k in defined.items()))
print("对齐了" if not bad else "★ 上面那些要补")
sys.exit(bad)

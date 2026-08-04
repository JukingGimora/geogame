#!/usr/bin/env python3
"""抓「模板把事件对象喂给了带参函数」这类 bug。

`@tap="startRun"` 不带括号时,Vue 会把点击事件当第一个实参传进去。如果 startRun
的第一个参数是 photoId,它收到的就是个事件对象——请求带着垃圾数据发出去,后端 422,
界面上只闪一个小 toast,看起来就是"按钮点了没反应"。

vue-tsc 查不出来:参数是可选的,类型上完全合法。冒烟脚本也查不出来:它测的是后端。
这个洞真实地让"开始一轮"整个失效过一次。

用法: python3 scripts/check-bindings.py     # 有问题时退出码非 0
"""
import pathlib
import re
import sys

SRC = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src"

BIND = re.compile(r'@(?:tap|click|change|confirm|input|longpress)="([A-Za-z_$][\w$]*)"')
TEMPLATE = re.compile(r"<template>(.*)</template>", re.S)

# 确实需要事件对象的处理函数:组件把数据放在 e.detail 里传出来。
# 加进来之前先确认它真的读了 e,而不是图省事消掉告警。
INTENTIONAL = {
    ("components/NativeMapPicker.vue", "onTap"),  # 读 e.detail 拿点击处的经纬度
}


def first_param(script: str, fn: str) -> str | None:
    """返回该函数第一个形参名;无参或找不到定义则返回 None。"""
    for pat in (
        rf"function\s+{re.escape(fn)}\s*\(([^)]*)\)",
        rf"const\s+{re.escape(fn)}\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>",
    ):
        m = re.search(pat, script)
        if m:
            params = m.group(1).strip()
            return params.split(",")[0].strip() if params else None
    return None


def main() -> int:
    problems = []
    for path in sorted(SRC.rglob("*.vue")):
        text = path.read_text(encoding="utf-8")
        tpl = TEMPLATE.search(text)
        if not tpl:
            continue
        rel = str(path.relative_to(SRC))
        # 只扫 <template>:script 里的注释提到 @tap="..." 不该算数
        for fn in set(BIND.findall(tpl.group(1))):
            if (rel, fn) in INTENTIONAL:
                continue
            p = first_param(text, fn)
            if p:
                problems.append((rel, fn, p))

    for rel, fn, param in problems:
        print(f'  ✗ {rel}: @tap="{fn}" 会把事件对象传给形参 `{param}`')
        print(f'      改成 @tap="{fn}()",或让该函数不接参数')

    if problems:
        print(f"\n{len(problems)} 处绑定会喂进事件对象")
        return 1
    print("模板事件绑定检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

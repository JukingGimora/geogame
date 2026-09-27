"""默认昵称。

线上 289 个用户里 279 个叫"旅行者"——榜单上一整列同名同脸，谁也认不出谁,
也就没人在乎自己排第几。所以默认名不能是占位符,得是个具体的人。

名字是随机挑的,不按 user_id 算。按 id 算的时候,注销之后 SQLite 会把刚腾出来的
id 再发给下一个人,于是他拿到一模一样的名字——看着像"没删掉"。
随机挑再避开已经有人用的,重名概率低,也没人能从名字反推出你是第几个进来的。
"""
import random

_ADJ = (
    "迷路的", "赶夜路的", "数星星的", "带伞的", "不问路的", "睡过站的",
    "追落日的", "坐末班车的", "捡石头的", "怕冷的", "爱下雨的", "走小路的",
    "不带地图的", "蹲在路边的", "总迟到的", "记路牌的", "听风的", "等花开的",
    "背旧包的", "拍云的", "绕远路的", "赶早班的", "认得出方言的", "在山口歇脚的",
    "逆着人流的", "只带一个包的", "把票根留着的", "认得北斗的", "爱坐靠窗的", "走错月台的",
    "等雪停的", "怕热的", "数电线杆的", "半夜下车的", "不吃早饭的", "把伞丢了的",
    "认得出海风的", "走到没路的", "睡在候车室的", "追着火车跑的", "爱问天气的", "记得每条河的",
    "不爱拍照的", "在渡口等船的", "翻过垭口的", "把外套系腰上的", "沿着铁轨走的", "爱赶集的",
)

_NOUN = (
    "骆驼", "旅人", "司机", "邮差", "船工", "背包客",
    "守夜人", "过路人", "拾荒者", "远客", "行脚僧", "赶车人",
    "测绘员", "牧羊人", "渡船客", "打更人", "制图师", "观海人",
    "记路人", "夜行客", "山民", "渔家", "纤夫", "挑夫",
    "修表匠", "采药人", "护林员", "灯塔看守", "补网人", "赶海人",
    "风筝客", "凉茶摊主", "收票员", "长途客", "车站猫", "候鸟",
    "邮路员", "巡道工", "赶集人", "渡口客",
)


_TOTAL = len(_ADJ) * len(_NOUN)
# 和 _TOTAL 互质,作用是打散:否则连号注册的人会连着拿到同一个名词,
# 同一天进来的一批新人在榜上会是一排"骆驼"
_STRIDE = 1103


def _compose(i: int) -> str:
    return f"{_ADJ[i % len(_ADJ)]}{_NOUN[i // len(_ADJ)]}"


def default_nickname(user_id: int) -> str:
    """user_id → 固定的默认昵称。只给老数据和 is_default 用,新人走 pick_nickname。"""
    n = max(user_id, 1) - 1
    i = (n * _STRIDE) % _TOTAL
    name = _compose(i)
    cycle = n // _TOTAL
    return name if cycle == 0 else f"{name}{cycle + 1}"


def pick_nickname(taken: set[str], tries: int = 12) -> str:
    """随机挑一个还没人用的名字。

    1920 个组合,几百个用户的时候随机撞车的概率不低,所以挑完要看一眼有没有被占。
    实在挑不到(名字池快满了)就在后面缀个编号,总之不让两个人同名。
    """
    for _ in range(tries):
        name = _compose(random.randrange(_TOTAL))
        if name not in taken:
            return name
    base = _compose(random.randrange(_TOTAL))
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def is_default(user_id: int, nickname: str | None) -> bool:
    """还没改过名的人,该被提示去设置一个自己的名字。"""
    return not nickname or nickname == "旅行者" or nickname == default_nickname(user_id)

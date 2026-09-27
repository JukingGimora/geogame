"""英文版要用的对照表。

H5 只发英文,但库里存的是中文——文化圈名、国名、提示③④都是。翻译放在读的时候做,
不在库里存两份:存两份就要迁移,而且以后加一种语言又要再迁一次。

翻不了的有两样,页面上会照原样显示中文:AI 线索(模型生成的)和用户自己写的故事。
那两样要英文得在审核时多跑一次模型、存双份,是另一笔钱。
"""
from fastapi import Header

DEFAULT_LANG = "zh"


def is_en(lang: str | None) -> bool:
    """这次请求要不要走英文。只认 en 开头,别的都按中文。"""
    return (lang or "").lower().startswith("en")


def lang_header(x_lang: str = Header(default=DEFAULT_LANG)) -> str:
    """X-Lang 请求头。前端每个请求都带,小程序带 zh、H5 带当前选的那个。"""
    return x_lang


CIRCLE_EN: dict[str, str] = {
    "东亚": "East Asia",
    "东南亚": "Southeast Asia",
    "南亚": "South Asia",
    "伊斯兰": "Islamic",
    "西欧": "Western",
    "东欧": "Orthodox",
    "非洲": "Africa",
    "拉美": "Latin America",
    "太平洋": "Pacific",
}

CIRCLE_DESC_EN: dict[str, str] = {
    "东亚": "Han characters on signs, tiled eaves, gridded fields and dense towers",
    "东南亚": "Gilded stupas, palms and banana leaves, tin roofs and rivers of scooters",
    "南亚": "Loud colour, densely carved temples, dust and crowded markets",
    "伊斯兰": "Domes and minarets, geometric pattern, dry ochre ground",
    "西欧": "Church spires, brick and stone facades, tidy signage and wires",
    "东欧": "Onion domes, Cyrillic lettering, heavy Soviet-era blocks",
    "非洲": "Red earth, savanna scrub, markets full of colour",
    "拉美": "Colonial pastel walls, Spanish signage, towns up steep hills",
    "太平洋": "Atolls and coconut palms, timber houses on stilts, endless sea",
}

# 提示④的方位。英文写成形容词放在国名前面("southern China"),
# 不写 "China · S" 那种缩写:后者要读者自己解码,而这一条是要花四成分买的
AREA_EN: dict[str, str] = {
    "西北": "north-western", "东北": "north-eastern",
    "西南": "south-western", "东南": "south-eastern",
    "西": "western", "东": "eastern", "南": "southern", "北": "northern",
    "": "central",
}

# 国名的形容词/族称形式。检查译文有没有泄露国家时,光比国名会漏——
# 中文只说"高原",译文写 "Chinese plateau" 一样是把国家说出来了。
# 只列题库里真出现过的那些国家,不做 161 个的全表
DEMONYM_EN: dict[str, tuple[str, ...]] = {
    "中国": ("Chinese",),
    "斐济": ("Fijian",),
    "俄罗斯": ("Russian",),
    "毛里求斯": ("Mauritian",),
    "斯里兰卡": ("Sri Lankan", "Lankan"),
    "乌兹别克斯坦": ("Uzbek",),
    "马来西亚": ("Malaysian", "Malay"),
    "南非": ("South African",),
    "亚美尼亚": ("Armenian",),
    "格鲁吉亚": ("Georgian",),
    "尼泊尔": ("Nepalese", "Nepali"),
    "哈萨克斯坦": ("Kazakh",),
    "土耳其": ("Turkish",),
    # 不写 "Lao":会把「黄老学」的 Huang-Lao 误报成老挝
    "老挝": ("Laotian",),
    "泰国": ("Thai",),
    "印度尼西亚": ("Indonesian",),
    "阿联酋": ("Emirati",),
    "新加坡": ("Singaporean",),
    "越南": ("Vietnamese",),
}

# 原文里出现这些词,就算已经点明了那个国家,译文跟着写出来不算泄露。
# 没有这张表,检查器会把「华人聚居」译成 Chinese-majority 也报成泄露——
# 一个吵到没人看的检查等于没有检查
SOURCE_ALIAS: dict[str, tuple[str, ...]] = {
    # 「中西样式」「华北平原」这类词,英文里绕不开 China/Chinese,不是译者加的
    "中国": ("中国", "中式", "中西", "中华", "中俄", "中原", "华人", "华北", "汉字",
             "汉地", "汉族", "汉文化", "汉式", "繁体", "简体", "民国", "大陆",
             "岭南", "唐代", "清代"),
    "俄罗斯": ("俄罗斯", "沙俄", "俄语", "中俄", "苏维埃", "苏联", "苏式"),
    "马来西亚": ("马来西亚", "马来"),
    "老挝": ("老挝",),
    "泰国": ("泰国", "泰文", "泰语"),
    "越南": ("越南",),
    "南非": ("南非",),
    "澳大利亚": ("澳大利亚", "澳洲"),
}

# 中文国名 → 英文国名。由 babel 的 CLDR 数据按 COUNTRY_CODE 生成,港澳台三条手写,
# 跟中文那边的说法保持一致
COUNTRY_EN: dict[str, str] = {
    "中国": "China", "日本": "Japan", "韩国": "South Korea",
    "朝鲜": "North Korea", "蒙古": "Mongolia", "中国台湾": "Taiwan, China",
    "中国香港": "Hong Kong, China", "中国澳门": "Macau, China", "泰国": "Thailand",
    "越南": "Vietnam", "柬埔寨": "Cambodia", "老挝": "Laos",
    "缅甸": "Myanmar (Burma)", "马来西亚": "Malaysia", "新加坡": "Singapore",
    "印度尼西亚": "Indonesia", "菲律宾": "Philippines", "文莱": "Brunei",
    "东帝汶": "Timor-Leste", "印度": "India", "巴基斯坦": "Pakistan",
    "孟加拉国": "Bangladesh", "尼泊尔": "Nepal", "斯里兰卡": "Sri Lanka",
    "不丹": "Bhutan", "马尔代夫": "Maldives", "沙特阿拉伯": "Saudi Arabia",
    "伊朗": "Iran", "伊拉克": "Iraq", "土耳其": "Turkey",
    "阿联酋": "United Arab Emirates", "埃及": "Egypt", "摩洛哥": "Morocco",
    "阿尔及利亚": "Algeria", "突尼斯": "Tunisia", "利比亚": "Libya",
    "约旦": "Jordan", "叙利亚": "Syria", "黎巴嫩": "Lebanon",
    "以色列": "Israel", "科威特": "Kuwait", "卡塔尔": "Qatar",
    "阿曼": "Oman", "也门": "Yemen", "阿富汗": "Afghanistan",
    "乌兹别克斯坦": "Uzbekistan", "哈萨克斯坦": "Kazakhstan", "土库曼斯坦": "Turkmenistan",
    "吉尔吉斯斯坦": "Kyrgyzstan", "塔吉克斯坦": "Tajikistan", "阿塞拜疆": "Azerbaijan",
    "法国": "France", "德国": "Germany", "英国": "United Kingdom",
    "意大利": "Italy", "西班牙": "Spain", "葡萄牙": "Portugal",
    "荷兰": "Netherlands", "比利时": "Belgium", "瑞士": "Switzerland",
    "奥地利": "Austria", "瑞典": "Sweden", "挪威": "Norway",
    "丹麦": "Denmark", "芬兰": "Finland", "爱尔兰": "Ireland",
    "冰岛": "Iceland", "希腊": "Greece", "卢森堡": "Luxembourg",
    "美国": "United States", "加拿大": "Canada", "澳大利亚": "Australia",
    "新西兰": "New Zealand", "俄罗斯": "Russia", "乌克兰": "Ukraine",
    "波兰": "Poland", "捷克": "Czechia", "斯洛伐克": "Slovakia",
    "匈牙利": "Hungary", "罗马尼亚": "Romania", "保加利亚": "Bulgaria",
    "塞尔维亚": "Serbia", "克罗地亚": "Croatia", "希腊北部": "Greece",
    "白俄罗斯": "Belarus", "立陶宛": "Lithuania", "拉脱维亚": "Latvia",
    "爱沙尼亚": "Estonia", "摩尔多瓦": "Moldova", "格鲁吉亚": "Georgia",
    "亚美尼亚": "Armenia", "波黑": "Bosnia & Herzegovina", "阿尔巴尼亚": "Albania",
    "北马其顿": "North Macedonia", "斯洛文尼亚": "Slovenia", "黑山": "Montenegro",
    "尼日利亚": "Nigeria", "埃塞俄比亚": "Ethiopia", "肯尼亚": "Kenya",
    "坦桑尼亚": "Tanzania", "南非": "South Africa", "加纳": "Ghana",
    "塞内加尔": "Senegal", "乌干达": "Uganda", "喀麦隆": "Cameroon",
    "科特迪瓦": "Côte d’Ivoire", "马里": "Mali", "苏丹": "Sudan",
    "刚果金": "Congo - Kinshasa", "安哥拉": "Angola", "莫桑比克": "Mozambique",
    "赞比亚": "Zambia", "津巴布韦": "Zimbabwe", "博茨瓦纳": "Botswana",
    "纳米比亚": "Namibia", "马达加斯加": "Madagascar", "卢旺达": "Rwanda",
    "马拉维": "Malawi", "布基纳法索": "Burkina Faso", "尼日尔": "Niger",
    "乍得": "Chad", "索马里": "Somalia", "毛里求斯": "Mauritius",
    "塞舌尔": "Seychelles", "墨西哥": "Mexico", "巴西": "Brazil",
    "阿根廷": "Argentina", "智利": "Chile", "秘鲁": "Peru",
    "哥伦比亚": "Colombia", "委内瑞拉": "Colombia", "厄瓜多尔": "Ecuador",
    "玻利维亚": "Bolivia", "巴拉圭": "Paraguay", "乌拉圭": "Uruguay",
    "古巴": "Cuba", "危地马拉": "Guatemala", "哥斯达黎加": "Costa Rica",
    "巴拿马": "Panama", "洪都拉斯": "Honduras", "尼加拉瓜": "Nicaragua",
    "萨尔瓦多": "El Salvador", "多米尼加": "Dominican Republic", "海地": "Haiti",
    "牙买加": "Jamaica", "伯利兹": "Belize", "苏里南": "Suriname",
    "圭亚那": "Guyana", "巴布亚新几内亚": "Papua New Guinea", "斐济": "Fiji",
    "所罗门群岛": "Solomon Islands", "瓦努阿图": "Vanuatu", "萨摩亚": "Samoa",
    "汤加": "Tonga", "密克罗尼西亚": "Micronesia", "帕劳": "Palau",
    "马绍尔群岛": "Marshall Islands", "新喀里多尼亚": "New Caledonia", "法属波利尼西亚": "French Polynesia",
    "关岛": "Guam", "夏威夷": "United States",
}

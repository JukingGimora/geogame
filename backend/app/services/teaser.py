"""提示①:上传者故事的开头。

原来是拦腰砍一半,砍在哪儿全看字数——"这里俄罗斯客人特别多,等…"、
"蜷缩在笼子…",句子断在半截上,读着像出了错。

现在按句子切:取到半程为止的整句,不足一句就整句给。宁可多给半句,
也不要给一个断掉的短语——这一条本来就是免费的,它的作用是把人拉进故事里,
不是精确控制泄露多少。
"""
_ENDS = "。！？；…!?;"
# 没有句号的短故事退而求其次,按逗号断
_SOFT = "，,、 "
MAX_CHARS = 60


def story_teaser(story: str) -> str:
    text = story.strip()
    if not text:
        return ""
    half = max(8, min(len(text) // 2, MAX_CHARS))
    head = text[:half]
    # 半程之内最后一个句末标点;没有就退到最后一个逗号
    cut = max((head.rfind(ch) for ch in _ENDS), default=-1)
    if cut < 4:
        cut = max((head.rfind(ch) for ch in _SOFT), default=-1)
    if cut >= 4:
        return text[:cut] + "…"
    # 整个前半段一个标点都没有:只能按字数切,但别切出个孤零零的连接词
    return head.rstrip("，,、的了和与及在是") + "…"

"""头像地址校验。

chooseAvatar 返回的是设备本地临时路径(`http://tmp/...`、`wxfile://...`),
直接存库的话只有当时那台设备能显示,别人看到的是黑框。正确做法是先传到
存储层换成真实地址(POST /auth/avatar),但**旧版小程序会一直留在用户手机上**,
仍然会把临时路径送上来,所以后端必须自己挡住。
"""
from urllib.parse import urlparse


def clean_avatar_url(value: str | None) -> str | None:
    """能用就原样返回,不能用返回 None。判断依据是"这是不是存储层产出的地址"。"""
    if not value:
        return None
    if value.startswith("/uploads/"):  # LocalStorage 模式下的相对路径
        return value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        return None
    # 临时路径的 host 是 tmp 这种没有点的东西;真实地址一定有域名
    host = parsed.hostname or ""
    return value if "." in host else None

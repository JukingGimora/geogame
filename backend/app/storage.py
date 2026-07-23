"""StorageProvider 接口。本地磁盘或阿里云OSS,由环境变量选择,业务代码不感知切换。"""
import io
import uuid

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from app.config import settings

register_heif_opener()
try:
    import pillow_avif  # noqa: F401
except ImportError:
    pass


def _process_image(data: bytes) -> bytes:
    """统一转 JPEG:先按 EXIF 方向转正,再抹除全部元数据,限长边。"""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


class LocalStorage:
    def save_image(self, data: bytes) -> str:
        key = f"{uuid.uuid4().hex}.jpg"
        (settings.upload_path / key).write_bytes(_process_image(data))
        return key

    def url(self, file_key: str) -> str:
        return f"/uploads/{file_key}"


class OSSStorage:
    def __init__(self) -> None:
        import oss2

        auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
        self._bucket = oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)
        host = settings.oss_endpoint.split("://")[-1]
        self._public_base = f"https://{settings.oss_bucket}.{host}"

    def save_image(self, data: bytes) -> str:
        key = f"{uuid.uuid4().hex}.jpg"
        self._bucket.put_object(key, _process_image(data))
        return key

    def url(self, file_key: str) -> str:
        return f"{self._public_base}/{file_key}"


def _build_storage():
    if settings.oss_bucket and settings.oss_access_key_id:
        return OSSStorage()
    return LocalStorage()


storage = _build_storage()

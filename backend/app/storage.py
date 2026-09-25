"""StorageProvider 接口。本地磁盘或阿里云OSS,由环境变量选择,业务代码不感知切换。"""
import io
import uuid

from PIL import ExifTags, Image, ImageOps
from pillow_heif import register_heif_opener

from app.config import settings

register_heif_opener()
try:
    import pillow_avif  # noqa: F401
except ImportError:
    pass


GPS_TAG = next(k for k, v in ExifTags.TAGS.items() if v == "GPSInfo")


def _ratio(value) -> float:
    return float(value[0]) / float(value[1]) if isinstance(value, tuple) else float(value)


def _dms(values, ref: str) -> float:
    deg, minutes, seconds = (_ratio(v) for v in values)
    dec = deg + minutes / 60 + seconds / 3600
    return -dec if ref in ("S", "W") else dec


def read_gps(data: bytes) -> tuple[float, float] | None:
    """照片自带的拍摄坐标,读不到就返回 None。

    必须在 process_image 之前读:那一步会把元数据全抹掉(这是故意的,
    上线的图不该带着拍摄者的设备信息)。经微信中转过的图 GPS 已经没了,
    所以"读不到"是常态之一,不是错误。
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            exif = img.getexif()
            gps = exif.get_ifd(GPS_TAG) if exif else None
        if not gps or 2 not in gps or 4 not in gps:
            return None
        lat = _dms(gps[2], gps.get(1, "N"))
        lng = _dms(gps[4], gps.get(3, "E"))
    except Exception:
        return None
    return (lat, lng) if -90 <= lat <= 90 and -180 <= lng <= 180 else None


def process_image(data: bytes) -> bytes:
    """统一转 JPEG:先按 EXIF 方向转正,再抹除全部元数据,限长边。

    跟 save() 分开是为了让"图片本身解不开"和"存储写不进去"能分别报错——
    合在一起的话 OSS 故障会被当成图片格式问题,用户只会徒劳地反复换图。
    """
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


class LocalStorage:
    def save(self, image: bytes) -> str:
        key = f"{uuid.uuid4().hex}.jpg"
        (settings.upload_path / key).write_bytes(image)
        return key

    def save_image(self, data: bytes) -> str:
        return self.save(process_image(data))

    def url(self, file_key: str) -> str:
        return f"/uploads/{file_key}"

    def read(self, file_key: str) -> bytes:
        return (settings.upload_path / file_key).read_bytes()

    def delete(self, file_key: str) -> None:
        path = settings.upload_path / file_key
        if path.exists():
            path.unlink()


class OSSStorage:
    def __init__(self) -> None:
        import oss2

        auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
        self._bucket = oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)
        host = settings.oss_endpoint.split("://")[-1]
        self._public_base = f"https://{settings.oss_bucket}.{host}"

    def save(self, image: bytes) -> str:
        key = f"{uuid.uuid4().hex}.jpg"
        self._bucket.put_object(key, image)
        return key

    def save_image(self, data: bytes) -> str:
        return self.save(process_image(data))

    def url(self, file_key: str) -> str:
        return f"{self._public_base}/{file_key}"

    def read(self, file_key: str) -> bytes:
        return self._bucket.get_object(file_key).read()

    def delete(self, file_key: str) -> None:
        self._bucket.delete_object(file_key)


def _build_storage():
    if settings.oss_bucket and settings.oss_access_key_id:
        return OSSStorage()
    return LocalStorage()


storage = _build_storage()

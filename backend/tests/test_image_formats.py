import io

import pytest
from PIL import Image

from tests.test_game_flow import login


def make_image(fmt: str, size=(300, 200), mode="RGB") -> bytes:
    buf = io.BytesIO()
    img = Image.new(mode, size, (90, 120, 160) if mode == "RGB" else None)
    if fmt == "HEIF":
        import pillow_heif

        pillow_heif.register_heif_opener()
    img.save(buf, format=fmt)
    return buf.getvalue()


FORMATS = [
    ("JPEG", "photo.jpg"),
    ("PNG", "photo.png"),
    ("WEBP", "photo.webp"),
    ("GIF", "photo.gif"),
    ("BMP", "photo.bmp"),
    ("TIFF", "photo.tiff"),
    ("HEIF", "photo.heic"),
    ("AVIF", "photo.avif"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt,filename", FORMATS)
async def test_upload_format_stored_as_jpeg(client, fmt, filename):
    headers = await login(client, f"device-fmt-{fmt.lower()}")
    r = await client.post(
        "/api/v1/photos",
        headers=headers,
        files={"file": (filename, make_image(fmt), "application/octet-stream")},
        data={"lat": 30.0, "lng": 110.0, "story": fmt},
    )
    assert r.status_code == 200, f"{fmt}: {r.text}"
    r = await client.get("/api/v1/photos/mine", headers=headers)
    assert r.json()[0]["url"].endswith(".jpg")


@pytest.mark.asyncio
async def test_rgba_png_converted(client):
    buf = io.BytesIO()
    Image.new("RGBA", (200, 200), (90, 120, 160, 128)).save(buf, format="PNG")
    headers = await login(client, "device-fmt-rgba")
    r = await client.post(
        "/api/v1/photos",
        headers=headers,
        files={"file": ("t.png", buf.getvalue(), "image/png")},
        data={"lat": 30.0, "lng": 110.0},
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_exif_orientation_applied(client, tmp_path):
    buf = io.BytesIO()
    img = Image.new("RGB", (400, 200), (90, 120, 160))
    exif = Image.Exif()
    exif[274] = 6
    img.save(buf, format="JPEG", exif=exif)

    headers = await login(client, "device-fmt-orient")
    r = await client.post(
        "/api/v1/photos",
        headers=headers,
        files={"file": ("rotated.jpg", buf.getvalue(), "image/jpeg")},
        data={"lat": 30.0, "lng": 110.0},
    )
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/photos/mine", headers=headers)
    key = r.json()[0]["url"].split("/")[-1]
    stored = Image.open(f"./test_uploads/{key}")
    assert stored.size == (200, 400)
    assert stored.getexif().get(274) is None


@pytest.mark.asyncio
async def test_garbage_bytes_rejected(client):
    headers = await login(client, "device-fmt-garbage")
    r = await client.post(
        "/api/v1/photos",
        headers=headers,
        files={"file": ("not_image.jpg", b"this is not an image at all", "image/jpeg")},
        data={"lat": 30.0, "lng": 110.0},
    )
    assert r.status_code == 422

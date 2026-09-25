#!/usr/bin/env python3
"""把电脑上一个文件夹里的照片批量导入题库(待审核)。

  python3 scripts/import_photos.py ~/Pictures/环球 --uploader 17
  python3 scripts/import_photos.py ~/Pictures/环球 --uploader 17 --dry-run

坐标从照片自带的 EXIF 里读,不用一张张在地图上点。**照片必须用隔空投送/数据线
传到电脑**——经微信中转的图,GPS 会被抹掉,导进来也没有坐标。

没有坐标的会被跳过并列在最后,那些只能手动补。故事留空,审核页里再写。
"""
import argparse
import json
import os
import sys
import urllib.request
import uuid
from pathlib import Path

from PIL import ExifTags, Image

try:  # iPhone 的 HEIC 不注册这个插件就读不出 EXIF,会误判成"没有坐标"
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    print("提示:未安装 pillow-heif,HEIC 照片读不到坐标(pip install pillow-heif)")

SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff", ".avif"}
GPS_TAG = next(k for k, v in ExifTags.TAGS.items() if v == "GPSInfo")


def _ratio(value) -> float:
    return float(value[0]) / float(value[1]) if isinstance(value, tuple) else float(value)


def _dms(values, ref: str) -> float:
    deg, minutes, seconds = (_ratio(v) for v in values)
    dec = deg + minutes / 60 + seconds / 3600
    return -dec if ref in ("S", "W") else dec


def read_gps(path: Path) -> tuple[float, float] | None:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            gps = exif.get_ifd(GPS_TAG) if exif else None
    except Exception:
        return None
    if not gps or 2 not in gps or 4 not in gps:
        return None
    try:
        return _dms(gps[2], gps.get(1, "N")), _dms(gps[4], gps.get(3, "E"))
    except Exception:
        return None


def post(base: str, token: str, path: Path, lat: float, lng: float, uploader: int) -> dict:
    boundary = uuid.uuid4().hex
    fields = {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "story": "", "uploader_id": str(uploader)}
    body = bytearray()
    for name, value in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n".encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n" + path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{base}/api/v1/admin/photos/import",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-Admin-Token": token},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--uploader", type=int, required=True, help="照片算在哪个用户名下")
    ap.add_argument("--base", default="https://tz5aq2zkxqhc.guyubao.com")
    ap.add_argument("--token", default=os.environ.get("GEOGAME_ADMIN_TOKEN", ""))
    ap.add_argument("--dry-run", action="store_true", help="只看有多少张带坐标,不上传")
    args = ap.parse_args()

    if not args.token and not args.dry_run:
        print("缺少管理口令:export GEOGAME_ADMIN_TOKEN=... 或用 --token", file=sys.stderr)
        return 2

    files = sorted(p for p in args.folder.rglob("*") if p.suffix.lower() in SUFFIXES)
    print(f"找到 {len(files)} 张照片")
    ok = dup = skipped = failed = 0
    no_gps: list[str] = []
    for i, path in enumerate(files, 1):
        coords = read_gps(path)
        if not coords:
            skipped += 1
            no_gps.append(path.name)
            continue
        lat, lng = coords
        if args.dry_run:
            ok += 1
            print(f"  [{i}/{len(files)}] {path.name}  {lat:.4f},{lng:.4f}")
            continue
        try:
            res = post(args.base, args.token, path, lat, lng, args.uploader)
        except Exception as e:
            failed += 1
            print(f"  ✗ {path.name}: {e}")
            continue
        if res.get("duplicate"):
            dup += 1
            print(f"  · {path.name} 已经传过了")
        else:
            ok += 1
            print(f"  ✓ [{i}/{len(files)}] {path.name} → {res.get('country')}·{res.get('circle')}")

    print(f"\n成功 {ok} · 重复 {dup} · 无坐标跳过 {skipped} · 失败 {failed}")
    if no_gps:
        print("\n这些没有坐标(多半是微信中转过),只能手动补:")
        for name in no_gps[:40]:
            print("  " + name)
        if len(no_gps) > 40:
            print(f"  …… 还有 {len(no_gps) - 40} 张")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

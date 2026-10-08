#!/usr/bin/env python3
"""resources/icon.png から Android のアプリアイコン一式を作る（要 Pillow）

    python3 scripts/make-icons.py [アイコン画像(.png/.ico)]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

APP = Path(__file__).resolve().parent.parent
RES = APP / "android" / "app" / "src" / "main" / "res"
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else APP / "resources" / "icon.png"

# 密度ごとのサイズ: (従来アイコン, アダプティブアイコンの前景)
SIZES = {"mdpi": (48, 108), "hdpi": (72, 162), "xhdpi": (96, 216), "xxhdpi": (144, 324), "xxxhdpi": (192, 432)}
# アダプティブアイコンは端末ごとに丸・角丸などで外側が切り取られるため、
# 画像は前景の中央 72% に置き、周りを背景色で埋める（安全領域は 66/108 ≒ 61%）
FOREGROUND_SCALE = 0.72

icon = Image.open(SRC).convert("RGBA")
if icon.width != icon.height:
    sys.exit("正方形の画像を指定してください")
bg = icon.getpixel((0, 0))  # 画像の角の色をアイコンの背景色にする
bg_hex = "#{:02X}{:02X}{:02X}".format(*bg[:3])


def resized(size):
    return icon.resize((size, size), Image.LANCZOS)


for density, (legacy, fg) in SIZES.items():
    d = RES / f"mipmap-{density}"
    d.mkdir(parents=True, exist_ok=True)
    resized(legacy).save(d / "ic_launcher.png")

    mask = Image.new("L", (legacy * 4, legacy * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, legacy * 4 - 1, legacy * 4 - 1), fill=255)
    round_icon = resized(legacy)
    round_icon.putalpha(mask.resize((legacy, legacy), Image.LANCZOS))
    round_icon.save(d / "ic_launcher_round.png")

    inner = round(fg * FOREGROUND_SCALE)
    canvas = Image.new("RGBA", (fg, fg), (0, 0, 0, 0))
    canvas.paste(resized(inner), ((fg - inner) // 2, (fg - inner) // 2))
    canvas.save(d / "ic_launcher_foreground.png")

(RES / "values" / "ic_launcher_background.xml").write_text(
    '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
    f'    <color name="ic_launcher_background">{bg_hex}</color>\n</resources>\n', "utf-8")
print(f"アイコンを作成しました（背景色 {bg_hex}）")

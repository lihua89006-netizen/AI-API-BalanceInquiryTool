"""生成应用图标 assets/app.ico（圆角蓝底 + 白色折线图）。

运行：python gen_icon.py
"""
import os

from PIL import Image, ImageDraw

SIZE = 256
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "app.ico")


def make_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角方形背景（深蓝渐变感：两层圆角）
    bg = (30, 88, 220, 255)
    d.rounded_rectangle([12, 12, 244, 244], radius=52, fill=bg)
    d.rounded_rectangle([12, 12, 244, 244], radius=52, outline=(70, 130, 255, 255), width=6)

    # 折线图（上升趋势）
    points = [(52, 178), (96, 138), (132, 152), (168, 104), (204, 84)]
    d.line(points, fill=(255, 255, 255, 255), width=16, joint="curve")

    # 坐标轴底线
    d.line([(40, 196), (216, 196)], fill=(255, 255, 255, 200), width=10)

    # 数据点小圆
    for x, y in points:
        r = 13
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255))
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=bg)

    return img


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img = make_icon()
    img.save(OUT, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("icon saved:", OUT)

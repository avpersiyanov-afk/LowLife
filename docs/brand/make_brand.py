# -*- coding: utf-8 -*-
"""Генератор фирменной графики LowLife (запускать обычным CPython 3 + Pillow).

    python docs/brand/make_brand.py

Логотип — монограмма «⅃Γ»: зеркальная L из «Low» (белая) и перевёрнутая L
из «Life» (оранжевая) на чёрном скруглённом квадрате. Название (wordmark) —
авторская графика `lowlife-wordmark-source.png`; скрипт её не перерисовывает,
только обрезает поля, чистит до строго чёрного/белого и красит «Γ» из «Life»
в оранжевый — как в монограмме.

Пишет:
  docs/brand/lowlife-logo.png       512×512 — README
  docs/brand/lowlife-logo.svg       вектор того же логотипа
  docs/brand/lowlife-wordmark.png   название — README
  LowLife.tab/_Themes.panel/About.pushbutton/icon.png      96×96 — кнопка на ленте
  LowLife.tab/_Themes.panel/About.pushbutton/logo.png      256×256 — окно «О программе»

В окне «О программе» название не картинкой, а шрифтом: буквы и их
повороты — lowlife.about.WORDMARK_LETTERS, сборка — lowlife.wordmark_wpf.
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ABOUT = os.path.join(ROOT, "LowLife.tab", "_Themes.panel", "About.pushbutton")

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
ORANGE = (240, 140, 40)

# Геометрия в координатах холста 512×512.
SIZE = 512
RADIUS = 110
LOW = [(176, 130, 234, 382), (76, 324, 234, 382)]     # ⅃: стойка + «нога» влево
LIFE = [(280, 130, 338, 382), (280, 130, 436, 188)]   # Γ: стойка + перекладина вправо


def logo(size, supersample=4):
    n = SIZE * supersample
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, n - 1, n - 1], radius=RADIUS * supersample, fill=BLACK)
    for rects, color in ((LOW, WHITE), (LIFE, ORANGE)):
        for x0, y0, x1, y1 in rects:
            d.rectangle([x0 * supersample, y0 * supersample,
                         x1 * supersample - 1, y1 * supersample - 1], fill=color)
    return im.resize((size, size), Image.LANCZOS)


def logo_svg():
    def rect(r, color):
        x0, y0, x1, y1 = r
        return '  <rect x="{}" y="{}" width="{}" height="{}" fill="#{:02x}{:02x}{:02x}"/>'.format(
            x0, y0, x1 - x0, y1 - y0, *color)
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {0} {0}" width="{0}" height="{0}">'.format(SIZE),
             '  <rect width="{0}" height="{0}" rx="{1}" fill="#000000"/>'.format(SIZE, RADIUS)]
    lines += [rect(r, WHITE) for r in LOW] + [rect(r, ORANGE) for r in LIFE]
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def wordmark(pad_ratio=0.08):
    src = Image.open(os.path.join(HERE, "lowlife-wordmark-source.png")).convert("L")
    # Чистим JPEG-шум: тёмное → чёрный, светлое → белый, края оставляем сглаженными.
    src = src.point(lambda v: 0 if v < 40 else 255 if v > 215 else int((v - 40) * 255 / 175))
    x0, y0, x1, y1 = src.point(lambda v: 255 if v > 128 else 0).getbbox()
    pad = int((y1 - y0) * pad_ratio * 2)
    box = (max(0, x0 - pad), max(0, y0 - pad), min(src.width, x1 + pad), min(src.height, y1 + pad))
    return accent_life_l(src.crop(box))


def _column_groups(gray):
    """Отрезки столбцов [x0, x1), в которых есть белое — по ним делятся буквы."""
    w, h = gray.size
    px = gray.load()
    filled = [any(px[x, y] > 128 for y in range(h)) for x in range(w)]
    groups, start = [], None
    for x, f in enumerate(filled + [False]):
        if f and start is None:
            start = x
        elif not f and start is not None:
            groups.append((start, x))
            start = None
    return groups


def accent_life_l(gray):
    """Красит «Γ» в оранжевый. По проекции столбцов буквы делятся на
    ⅃ | ow (o и w перекрываются) | Γ | i | Fe (F касается e) — «Γ» третья."""
    groups = _column_groups(gray)
    assert len(groups) == 5, "не удалось найти буквы названия: {}".format(groups)
    x0, x1 = groups[2]
    rgb = Image.merge("RGB", (gray, gray, gray))
    tint = Image.new("RGB", (x1 - x0, gray.height), ORANGE)
    # Пиксели буквы: белый → оранжевый, сглаженный край → смесь с чёрным.
    region = gray.crop((x0, 0, x1, gray.height))
    rgb.paste(Image.composite(tint, Image.new("RGB", tint.size, BLACK), region), (x0, 0))
    return rgb


def main():
    logo(512).save(os.path.join(HERE, "lowlife-logo.png"))
    with open(os.path.join(HERE, "lowlife-logo.svg"), "w") as f:
        f.write(logo_svg())
    wm = wordmark()
    wm.save(os.path.join(HERE, "lowlife-wordmark.png"))
    logo(96).save(os.path.join(ABOUT, "icon.png"))
    logo(256).save(os.path.join(ABOUT, "logo.png"))


if __name__ == "__main__":
    main()

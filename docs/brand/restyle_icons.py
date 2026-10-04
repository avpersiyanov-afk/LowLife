# -*- coding: utf-8 -*-
"""Иконки кнопок в фирменном стиле — светлая и тёмная версии (CPython 3 + Pillow).

    python docs/brand/restyle_icons.py                      # перекрасить все
    python docs/brand/restyle_icons.py --preview out.png    # только лист превью

Исходник — иконка в прежнем стиле (светлый фон, синие линии, оранжевый акцент).
Из неё получаются две, рисунок тот же, меняется только палитра:
  icon.png       — светлая тема Revit: светлый фон, почти чёрные линии;
  icon.dark.png  — тёмная тема Revit: чёрный фон, белые линии (как логотип).
pyRevit сам берёт icon.dark.png, когда в Revit включена тёмная тема.
Оранжевый акцент в обеих — цвет логотипа; красный (кнопки удаления) остаётся
красным. Попиксельно:
  * «чернила» (синий, серый, белый) → от цвета фона к цвету линий по тому,
    насколько пиксель темнее исходного фона (самый тёмный синий = линии;
    светлые заливки — полутон; белые вставки — цвет фона);
  * оранжевый/красный → от фона к акценту по насыщенности.
Иконки, у которых уже есть icon.dark.png, пропускаются — повторный запуск
ничего не меняет.
"""
import colorsys
import glob
import os
import sys
from collections import Counter

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

ORANGE = (240, 140, 40)
RED = (235, 75, 65)
LIGHT = {"bg": (244, 244, 244), "ink": (26, 26, 26), "red": (210, 55, 50)}
DARK = {"bg": (0, 0, 0), "ink": (255, 255, 255), "red": RED}
SOURCE_RED = (200, 50, 45)


def pyrevit_icons():
    return sorted(glob.glob(os.path.join(ROOT, "LowLife.tab", "**", "icon.png"), recursive=True))


def dark_path(path):
    return path[:-len(".png")] + ".dark.png"


def _pixels(im):
    get = getattr(im, "get_flattened_data", None) or im.getdata
    return list(get())


def _lum(c):
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255.0


def _lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def _dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _kind(c):
    h, l, s = colorsys.rgb_to_hls(*[v / 255.0 for v in c])
    deg = h * 360
    if s > 0.25 and 0.08 < l < 0.97:
        if 18 <= deg <= 50:
            return "orange"
        if deg < 12 or deg > 345:
            return "red"
    return "ink"


def background(im):
    opaque = Counter(px[:3] for px in _pixels(im) if px[3] == 255)
    return opaque.most_common(1)[0][0] if opaque else (255, 255, 255)


def is_brand_mark(im):
    """Логотип (и всё, что уже на чёрном фоне) не перекрашиваем."""
    return _lum(background(im)) < 0.15


def restyle(im, palette):
    im = im.convert("RGBA")
    src_bg = background(im)
    px = _pixels(im)
    bg, ink = palette["bg"], palette["ink"]
    out = []
    if _lum(src_bg) < 0.7:
        # Цветной фон (красная «корзина»): фон → фон темы, светлый рисунок → красный.
        for r, g, b, a in px:
            t = _dist((r, g, b), src_bg) / max(1.0, _dist((255, 255, 255), src_bg))
            out.append(_lerp(bg, palette["red"], t) + (a,))
    else:
        lb = _lum(src_bg)
        inks = sorted(_lum(p[:3]) for p in px if p[3] > 200 and _kind(p[:3]) == "ink")
        darkest = inks[max(0, len(inks) // 50)] if inks else 0.0  # 2-й перцентиль, а не выброс
        span = max(0.15, lb - darkest)
        for r, g, b, a in px:
            c = (r, g, b)
            kind = _kind(c)
            if kind == "ink":
                out.append(_lerp(bg, ink, (lb - _lum(c)) / span) + (a,))
            else:
                # Сила акцента — по насыщенности (max−min), а не по яркости:
                # светлая оранжевая заливка остаётся чисто оранжевой, а
                # сглаженный край (смесь со светлым фоном) — частичной.
                target = ORANGE if kind == "orange" else palette["red"]
                ref = ORANGE if kind == "orange" else SOURCE_RED
                t = (max(c) - min(c)) / (0.75 * (max(ref) - min(ref)))
                out.append(_lerp(bg, target, t) + (a,))
    res = Image.new("RGBA", im.size)
    res.putdata(out)
    return res


def preview(out_path, cols=10, cell=72):
    paths = pyrevit_icons()
    rows = (len(paths) + cols - 1) // cols
    gap = 20
    sheet = Image.new("RGB", (cols * cell * 3 + gap * 2, rows * cell), (238, 240, 243))
    # Средняя и правая колонки — на подложках цвета ленты Revit (светлая/тёмная).
    dark_x = cols * cell * 2 + gap * 2
    sheet.paste((59, 68, 83), (dark_x - gap // 2, 0, sheet.width, sheet.height))
    for i, p in enumerate(paths):
        src = Image.open(p).convert("RGBA")
        dp = dark_path(p)
        if os.path.exists(dp):
            light, dark = src, Image.open(dp).convert("RGBA")
        elif is_brand_mark(src):
            light = dark = src
        else:
            light, dark = restyle(src, LIGHT), restyle(src, DARK)
        x, y = (i % cols) * cell, (i // cols) * cell
        for dx, img in ((0, src), (cols * cell + gap, light), (dark_x, dark)):
            t = img.resize((64, 64), Image.LANCZOS)
            sheet.paste(t, (x + dx + 4, y + 4), t)
    sheet.save(out_path)


def main(argv):
    if "--preview" in argv:
        preview(argv[argv.index("--preview") + 1])
        return
    done = skipped = 0
    for p in pyrevit_icons():
        src = Image.open(p).convert("RGBA")
        if os.path.exists(dark_path(p)) or is_brand_mark(src):
            skipped += 1
            continue
        restyle(src, DARK).save(dark_path(p))
        restyle(src, LIGHT).save(p)
        done += 1
    print("перекрашено: {}, пропущено: {}".format(done, skipped))


if __name__ == "__main__":
    main(sys.argv[1:])

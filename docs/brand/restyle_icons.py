# -*- coding: utf-8 -*-
"""Перекраска иконок кнопок в фирменный стиль логотипа (CPython 3 + Pillow).

    python docs/brand/restyle_icons.py            # перекрасить все
    python docs/brand/restyle_icons.py --preview out.png   # только лист «было/стало»

Старый стиль: светлый скруглённый фон, синие линии, оранжевый акцент.
Новый (как монограмма ⅃Γ): чёрный фон, белые линии, тот же оранжевый акцент.
Рисунок не меняется — только палитра, попиксельно:
  * «чернила» (синий, серый, белый) → оттенок от чёрного к белому по тому,
    насколько пиксель темнее фона (самый тёмный синий иконки = чисто белый;
    светлые заливки — тёмно-серые, белые вставки — чёрные);
  * оранжевый → оранжевый логотипа той же силы;
  * красный (кнопки удаления) → красный, чтобы не терять предупреждение.
Иконки, которые уже на тёмном фоне (логотип, перекрашенные), пропускаются —
скрипт можно запускать повторно.
"""
import colorsys
import glob
import os
import sys
from collections import Counter

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
ORANGE = (240, 140, 40)
RED = (235, 75, 65)


def icon_paths():
    paths = sorted(glob.glob(os.path.join(ROOT, "LowLife.tab", "**", "icon.png"), recursive=True))
    paths += sorted(glob.glob(os.path.join(ROOT, "csharp", "FamilyCatalog", "*.png")))
    return paths


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


def _pixels(im):
    get = getattr(im, "get_flattened_data", None) or im.getdata
    return list(get())


def background(im):
    opaque = Counter(px[:3] for px in _pixels(im) if px[3] == 255)
    return opaque.most_common(1)[0][0] if opaque else WHITE


def is_restyled(im):
    return _lum(background(im)) < 0.15


def restyle(im):
    im = im.convert("RGBA")
    bg = background(im)
    px = _pixels(im)
    if _lum(bg) < 0.7:
        # Цветной фон (красная «корзина»): фон → чёрный, светлый рисунок → красный.
        out = []
        for r, g, b, a in px:
            t = _dist((r, g, b), bg) / max(1.0, _dist(WHITE, bg))
            out.append(_lerp(BLACK, RED, t) + (a,))
    else:
        lb = _lum(bg)
        inks = sorted(_lum(p[:3]) for p in px if p[3] > 200 and _kind(p[:3]) == "ink")
        darkest = inks[max(0, len(inks) // 50)] if inks else 0.0  # 2-й перцентиль, а не выброс
        span = max(0.15, lb - darkest)
        out = []
        for r, g, b, a in px:
            c = (r, g, b)
            kind = _kind(c)
            if kind == "ink":
                out.append(_lerp(BLACK, WHITE, (lb - _lum(c)) / span) + (a,))
            else:
                # Сила акцента — по насыщенности (max−min), а не по яркости:
                # светлая оранжевая заливка остаётся чисто оранжевой, а
                # сглаженный край (смесь со светлым фоном) — частичной.
                target = ORANGE if kind == "orange" else RED
                ref = ORANGE if kind == "orange" else (200, 50, 45)
                t = (max(c) - min(c)) / (0.75 * (max(ref) - min(ref)))
                out.append(_lerp(BLACK, target, t) + (a,))
    res = Image.new("RGBA", im.size)
    res.putdata(out)
    return res


def preview(paths, out_path, cols=10, cell=72):
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell * 2 + 20, rows * cell), (245, 245, 245))
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGBA")
        new = im if is_restyled(im) else restyle(im)
        x, y = (i % cols) * cell, (i // cols) * cell
        for dx, img in ((0, im), (cols * cell + 20, new)):
            t = img.resize((64, 64), Image.LANCZOS)
            sheet.paste(t, (x + dx + 4, y + 4), t)
    sheet.save(out_path)


def main(argv):
    paths = icon_paths()
    if "--preview" in argv:
        preview(paths, argv[argv.index("--preview") + 1])
        return
    done = 0
    for p in paths:
        im = Image.open(p)
        if is_restyled(im.convert("RGBA")):
            continue
        restyle(im).save(p)
        done += 1
    print("перекрашено: {}, пропущено: {}".format(done, len(paths) - done))


if __name__ == "__main__":
    main(sys.argv[1:])

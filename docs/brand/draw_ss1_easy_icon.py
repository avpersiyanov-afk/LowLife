# -*- coding: utf-8 -*-
"""Иконка кнопки «СС1-8Mile» (CPython 3 + Pillow).

    python docs/brand/draw_ss1_easy_icon.py

Шарж-персонаж (платиновый ёжик, оранжевое худи, микрофон) — выбор
пользователя, а не рисунок действия кнопки, поэтому в draw_icons.py её нет
и restyle_icons.py её не трогает (он перекрасил бы светлые волосы в серый):
скрипт сам пишет обе версии — icon.png (светлая тема) и icon.dark.png
(тёмная) в фирменной палитре.
"""
import os

from PIL import Image, ImageChops, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
BUTTON = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                      "LowLife.tab", "SS1.panel", "SS1Easy.pushbutton")

K = 8
S = 96 * K
ORANGE = (240, 140, 40)
SKIN = (240, 200, 170)
SHADE = (214, 168, 138)
HAIR = (250, 236, 160)
HAIR_DARK = (226, 200, 110)
MIC = (70, 72, 78)
SILVER = (198, 200, 205)
MESH = (120, 122, 128)
LIGHT = {"bg": (244, 244, 244, 255), "ink": (26, 26, 26)}
DARK = {"bg": (0, 0, 0, 255), "ink": (255, 255, 255)}


def s(*v):
    return [x * K for x in v]


def draw(theme):
    bg, ink = theme["bg"], theme["ink"]
    w = int(2.2 * K)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle(s(2, 2, 94, 94), radius=16 * K, fill=bg)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(s(2, 2, 94, 94), radius=16 * K, fill=255)
    lay = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    g = ImageDraw.Draw(lay)

    # худи, шея, уши, голова
    g.rounded_rectangle(s(14, 74, 82, 110), radius=20 * K, fill=ORANGE, outline=ink, width=w)
    g.polygon(s(36, 74, 48, 90, 60, 74), fill=ink)
    g.rectangle(s(40, 62, 56, 76), fill=SHADE, outline=ink, width=w)
    for x in (25, 71):
        g.ellipse(s(x - 5, 40, x + 5, 54), fill=SKIN, outline=ink, width=w)
    g.rounded_rectangle(s(27, 18, 69, 70), radius=19 * K, fill=SKIN, outline=ink, width=w)

    # платиновый ёжик: верх головы, срезанный по линии волос
    head = Image.new("L", (S, S), 0)
    ImageDraw.Draw(head).rounded_rectangle(s(27, 18, 69, 70), radius=19 * K, fill=255)
    cut = Image.new("L", (S, S), 0)
    ImageDraw.Draw(cut).polygon(s(20, 10, 76, 10, 76, 33, 66, 33, 62, 29, 48, 30,
                                  34, 29, 30, 33, 20, 33), fill=255)
    lay.paste(Image.new("RGBA", (S, S), HAIR + (255,)), (0, 0), ImageChops.multiply(head, cut))
    g.line(s(29, 33, 34, 29, 48, 30, 62, 29, 67, 33), fill=HAIR_DARK, width=int(1.4 * K), joint="curve")
    g.rounded_rectangle(s(27, 18, 69, 70), radius=19 * K, outline=ink, width=w)
    for x in range(38, 60, 4):
        g.line(s(x, 22, x + 0.8, 25.5), fill=HAIR_DARK, width=int(1 * K))

    # брови, прищур, нос, ухмылка, щетина
    g.line(s(35, 38, 44, 37), fill=HAIR_DARK, width=int(2.4 * K))
    g.line(s(52, 36, 61, 38), fill=HAIR_DARK, width=int(2.4 * K))
    g.line(s(36, 43, 43, 43), fill=ink, width=int(2.4 * K))
    g.line(s(53, 43, 60, 43), fill=ink, width=int(2.4 * K))
    g.line(s(48, 44, 46, 53, 50, 53), fill=SHADE, width=int(2 * K), joint="curve")
    g.line(s(41, 60, 50, 60, 56, 57), fill=ink, width=int(2.2 * K), joint="curve")
    for x, y in [(36, 62), (40, 65), (46, 66), (52, 66), (57, 63), (60, 59), (34, 58)]:
        g.ellipse(s(x - .6, y - .6, x + .6, y + .6), fill=SHADE)

    # кулак с микрофоном у уголка рта
    g.polygon(s(31, 64, 38, 64, 36, 80, 30, 80), fill=MIC)
    g.line(s(31, 64, 38, 64, 36, 80, 30, 80, 31, 64), fill=ink, width=w, joint="curve")
    g.rounded_rectangle(s(23, 72, 41, 88), radius=6 * K, fill=SKIN, outline=ink, width=w)
    for y in (76, 80, 84):
        g.line(s(32, y, 40, y), fill=SHADE, width=int(1 * K))
    g.ellipse(s(27, 49, 42, 64), fill=SILVER, outline=ink, width=w)
    for x in (31, 34.5, 38):
        g.line(s(x, 50.5, x, 62.5), fill=MESH, width=int(0.9 * K))
    for y in (53, 56.5, 60):
        g.line(s(28.5, y, 40.5, y), fill=MESH, width=int(0.9 * K))

    im.paste(lay, (0, 0), ImageChops.multiply(lay.split()[3], mask))
    return im.resize((96, 96), Image.LANCZOS)


def main():
    draw(LIGHT).save(os.path.join(BUTTON, "icon.png"))
    draw(DARK).save(os.path.join(BUTTON, "icon.dark.png"))


if __name__ == "__main__":
    main()

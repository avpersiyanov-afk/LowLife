# -*- coding: utf-8 -*-
"""Иконки кнопок, нарисованные заново (CPython 3 + Pillow).

    python docs/brand/draw_icons.py            # записать icon.png и перекрасить
    python docs/brand/draw_icons.py --preview out.png

Рисует в прежней палитре (светлый фон, синие линии, оранжевый акцент) —
это исходник для restyle_icons.py: после записи icon.png скрипт удаляет
старый icon.dark.png и запускает restyle_icons, который делает светлую и
тёмную версии в фирменной палитре.

Сюда попадают иконки, у которых старый рисунок не соответствовал кнопке
(корзина у «Подсветить без цепи», значок адресов у цепей шлейфов и т.п.).
Координаты — в сетке 96×96, рисуется с 4-кратным запасом и уменьшается.
"""
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TAB = os.path.join(ROOT, "LowLife.tab")

BG = (235, 241, 245)
BLUE = (48, 112, 186)
ORANGE = (240, 140, 40)
PALE_ORANGE = (250, 205, 160)
WHITE = (248, 250, 253)
K = 4
LW = 5


class Canvas(object):
    def __init__(self):
        self.im = Image.new("RGBA", (96 * K, 96 * K), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)
        self.d.rounded_rectangle([2 * K, 2 * K, 94 * K - 1, 94 * K - 1], radius=16 * K, fill=BG)

    @staticmethod
    def _s(pts):
        return [(x * K, y * K) for x, y in pts]

    def line(self, pts, color=BLUE, w=LW):
        pts = self._s(pts)
        self.d.line(pts, fill=color, width=int(w * K), joint="curve")
        r = w * K / 2.0
        for x, y in (pts[0], pts[-1]):
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    def dashed(self, a, b, color=BLUE, w=3, dash=5, gap=4):
        (x0, y0), (x1, y1) = a, b
        length = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        t = 0.0
        while t < length:
            e = min(length, t + dash)
            self.d.line(self._s([(x0 + ux * t, y0 + uy * t), (x0 + ux * e, y0 + uy * e)]),
                        fill=color, width=int(w * K))
            t = e + gap

    def rect(self, box, outline=BLUE, fill=None, w=LW, r=3):
        x0, y0, x1, y1 = box
        self.d.rounded_rectangle([x0 * K, y0 * K, x1 * K, y1 * K], radius=r * K,
                                 outline=outline, fill=fill, width=int(w * K) if outline else 0)

    def circle(self, c, r, outline=BLUE, fill=None, w=LW):
        x, y = c
        self.d.ellipse([(x - r) * K, (y - r) * K, (x + r) * K, (y + r) * K],
                       outline=outline, fill=fill, width=int(w * K) if outline else 0)

    def polygon(self, pts, fill=None, outline=None, w=LW):
        self.d.polygon(self._s(pts), fill=fill)
        if outline:
            self.line(list(pts) + [pts[0]], outline, w)

    def magnifier(self, c=(64, 64), r=13, handle=15):
        x, y = c
        self.circle(c, r, BLUE, WHITE, LW)
        a = math.radians(45)
        self.line([(x + r * math.cos(a), y + r * math.sin(a)),
                   (x + (r + handle) * math.cos(a), y + (r + handle) * math.sin(a))], BLUE, 7)

    def badge(self, c=(72, 72), r=19):
        self.circle(c, r, BLUE, WHITE, 4)

    def save(self, path):
        self.im.resize((96, 96), Image.LANCZOS).save(path)


def _graph(c):
    """Граф устройств — общий знак структурных схем (как у СОТ/СПС)."""
    c.line([(24, 26), (44, 44)])
    c.line([(44, 44), (64, 32)])
    c.line([(44, 44), (34, 64)])
    for p in ((24, 26), (44, 44), (64, 32)):
        c.circle(p, 8, BLUE, WHITE, 4.5)
    c.circle((34, 64), 8, None, ORANGE)


def schematic_scs(c):
    _graph(c)
    c.badge()
    # Розетка RJ45: корпус с выступом-защёлкой снизу и контактами.
    c.polygon([(61, 64), (83, 64), (83, 78), (77, 78), (77, 82), (67, 82), (67, 78), (61, 78)],
              outline=BLUE, w=3)
    for x in (66, 70, 74, 78):
        c.line([(x, 67), (x, 71)], ORANGE if x in (70, 74) else BLUE, 2)


def schematic_skud(c):
    _graph(c)
    c.badge()
    # Ключ: кольцо и бородка.
    c.circle((64, 72), 5.5, BLUE, None, 3)
    c.line([(69.5, 72), (83, 72)], BLUE, 3)
    c.line([(79, 72), (79, 78)], ORANGE, 3)
    c.line([(83, 72), (83, 77)], ORANGE, 3)


def highlight_no_circuit(c):
    # Провод подходит к устройству, но обрывается; устройство подсвечено.
    c.line([(8, 50), (26, 50)])
    c.line([(26, 50), (32, 42)], ORANGE, 4)
    c.line([(32, 58), (38, 50)], ORANGE, 4)
    c.rect((44, 20, 88, 80), ORANGE, None, 8, 12)
    c.rect((50, 26, 82, 74), BLUE, WHITE, 5, 6)
    c.circle((50, 50), 6, BLUE, WHITE, 4)
    c.circle((66, 50), 6, None, BLUE)


def loop_circuits(c):
    # Панель, из которой выходит и в которую возвращается замкнутый шлейф
    # с устройствами на нём (одно выделено).
    c.d.rounded_rectangle([20 * K, 22 * K, 84 * K, 74 * K], radius=16 * K,
                          outline=BLUE, width=int(4.5 * K))
    c.rect((8, 32, 32, 64), BLUE, WHITE, 5, 3)
    c.circle((20, 48), 4, None, ORANGE)
    c.circle((56, 24), 7, BLUE, WHITE, 4.5)
    c.circle((84, 48), 7, BLUE, WHITE, 4.5)
    c.circle((56, 72), 7.5, None, ORANGE)


def camera_fov(c):
    # План: камера в углу и сектор её обзора.
    apex = (20, 76)
    r = 64
    a0, a1 = -78, -22
    pts = [apex] + [(apex[0] + r * math.cos(math.radians(a)), apex[1] + r * math.sin(math.radians(a)))
                    for a in range(a0, a1 + 1, 2)]
    c.polygon(pts, fill=PALE_ORANGE)
    c.line([pts[0], pts[1]], ORANGE, 3.5)
    c.line([pts[0], pts[-1]], ORANGE, 3.5)
    c.d.arc([(apex[0] - r) * K, (apex[1] - r) * K, (apex[0] + r) * K, (apex[1] + r) * K],
            a0, a1, fill=ORANGE, width=int(3.5 * K))
    # Корпус камеры, повёрнутый по биссектрисе сектора.
    ang = math.radians((a0 + a1) / 2.0)
    ux, uy = math.cos(ang), math.sin(ang)
    vx, vy = -uy, ux
    def p(t, s):
        return (apex[0] + ux * t + vx * s, apex[1] + uy * t + vy * s)
    c.polygon([p(-14, -7), p(4, -7), p(4, 7), p(-14, 7)], fill=BLUE)
    c.polygon([p(4, -4), p(10, -7), p(10, 7), p(4, 4)], fill=BLUE)
    c.circle(p(-8, 0), 2.5, None, WHITE)


def camera_view(c):
    # Видоискатель: уголки кадра, внутри — перспектива помещения, индикатор записи.
    for (x, y, dx, dy) in ((12, 18, 1, 1), (84, 18, -1, 1), (12, 78, 1, -1), (84, 78, -1, -1)):
        c.line([(x, y + 12 * dy), (x, y), (x + 12 * dx, y)], BLUE, 5)
    c.rect((38, 38, 58, 58), BLUE, WHITE, 3.5, 1)
    for (x0, y0, x1, y1) in ((22, 28, 38, 38), (74, 28, 58, 38), (22, 68, 38, 58), (74, 68, 58, 58)):
        c.line([(x0, y0), (x1, y1)], BLUE, 3)
    c.circle((22, 28), 4, None, ORANGE)


def diag_schematic(c):
    # Схема (контроллер и устройства) под лупой.
    c.rect((10, 12, 30, 26), BLUE, WHITE, 4, 2)
    c.line([(20, 26), (20, 62)], BLUE, 4)
    for y in (40, 56):
        c.line([(20, y), (34, y)], BLUE, 4)
        c.rect((34, y - 5, 44, y + 5), BLUE, WHITE, 3.5, 1.5)
    c.magnifier((62, 52), 15, 16)
    c.circle((62, 52), 5, None, ORANGE)


def diag_connectors(c):
    # Электрический коннектор (вилка) под лупой.
    c.rect((10, 28, 34, 52), BLUE, WHITE, 5, 4)
    c.line([(16, 18), (16, 28)], BLUE, 5)
    c.line([(28, 18), (28, 28)], BLUE, 5)
    c.line([(22, 52), (22, 62), (36, 62)], BLUE, 4)
    c.magnifier((60, 50), 15, 16)
    c.circle((60, 50), 5, None, ORANGE)


def door_room(c):
    # Дверь (точка прохода) и метка помещения.
    c.rect((14, 22, 46, 84), BLUE, None, 5, 2)
    c.polygon([(18, 26), (40, 32), (40, 86), (18, 80)], fill=WHITE, outline=BLUE, w=4)
    c.circle((35, 58), 3, None, BLUE)
    c.line([(8, 84), (88, 84)], BLUE, 5)
    # Метка-булавка помещения.
    cx, cy, r = 68, 34, 13
    c.polygon([(cx - r * 0.75, cy + r * 0.66), (cx, cy + 30), (cx + r * 0.75, cy + r * 0.66)], fill=ORANGE)
    c.circle((cx, cy), r, None, ORANGE)
    c.circle((cx, cy), 5, None, WHITE)


def diag_tag(c):
    """«Диагностика марки»: помещение с маркой (как «Марки помещений») под лупой."""
    c.rect((10, 30, 50, 80), BLUE, None, 5, 2)
    c.line([(44, 36), (60, 22)], BLUE, 3)
    c.rect((56, 12, 86, 28), None, BLUE, 0, 4)
    c.line([(62, 20), (72, 20)], WHITE, 3)
    c.circle((79, 20), 3, None, ORANGE)
    c.magnifier((58, 60), 14, 14)
    c.circle((58, 60), 5, None, ORANGE)


ICONS = [
    ("CircuitsDelete.panel/HighlightNoCircuit.pushbutton", highlight_no_circuit),
    ("SCS.panel/BuildScsSchematic.pushbutton", schematic_scs),
    ("SKUD.panel/BuildSkudSchematic.pushbutton", schematic_skud),
    ("SKUD.panel/AssignSkudRooms.pushbutton", door_room),
    ("CircuitsSPA.panel/BuildLoopCircuitsSPA.pushbutton", loop_circuits),
    ("CircuitsSPS.panel/BuildLoopCircuitsSPS.pushbutton", loop_circuits),
    ("SOUE.panel/BuildLoopCircuits.pushbutton", loop_circuits),
    ("SOT.panel/CameraFov.pushbutton", camera_fov),
    ("SOT.panel/CameraPreviewView.pushbutton", camera_view),
    ("SKUD.panel/InspectSchematicDevices.pushbutton", diag_schematic),
    ("SPS.panel/InspectConnectors.pushbutton", diag_connectors),
    ("ToolsRooms.panel/DiagnoseRoomTag.pushbutton", diag_tag),
]


def render(fn):
    c = Canvas()
    fn(c)
    return c


def main(argv):
    if "--preview" in argv:
        out = argv[argv.index("--preview") + 1]
        sheet = Image.new("RGB", (len(ICONS) * 110, 110), (255, 255, 255))
        for i, (_, fn) in enumerate(ICONS):
            im = render(fn).im.resize((96, 96), Image.LANCZOS)
            sheet.paste(im, (i * 110 + 7, 7), im)
        sheet.save(out)
        return
    for rel, fn in ICONS:
        folder = os.path.join(TAB, *rel.split("/"))
        render(fn).save(os.path.join(folder, "icon.png"))
        dark = os.path.join(folder, "icon.dark.png")
        if os.path.exists(dark):
            os.remove(dark)
    subprocess.check_call([sys.executable, os.path.join(HERE, "restyle_icons.py")])


if __name__ == "__main__":
    main(sys.argv[1:])

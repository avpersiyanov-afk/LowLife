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


def feedback(c):
    """«Обратная связь»: облачко сообщения с оранжевым восклицательным знаком."""
    c.rect((12, 16, 84, 64), BLUE, WHITE, 5, 12)
    c.polygon([(28, 61), (26, 82), (46, 61)], fill=BLUE)
    c.polygon([(31, 59), (30, 74), (42, 59)], fill=WHITE)
    c.line([(48, 26), (48, 44)], ORANGE, 7)
    c.circle((48, 54), 4.2, None, ORANGE)


def ribbon_search(c):
    """«Поиск»: кнопки ленты сеткой, одна найдена (оранжевая), над ней лупа."""
    for x, y in ((12, 12), (40, 12), (12, 40)):
        c.rect((x, y, x + 22, y + 22), BLUE, WHITE, 4, 5)
    c.rect((40, 40, 62, 62), ORANGE, PALE_ORANGE, 4, 5)
    c.magnifier((51, 51), 17, 18)
    c.rect((45, 45, 57, 57), None, ORANGE, 0, 3)


def favorites(c):
    """«Избранное»: панель ленты с кнопками, на одной — оранжевая звезда."""
    c.rect((10, 22, 86, 78), BLUE, WHITE, 5, 8)
    c.line([(10, 66), (86, 66)], BLUE, 4)
    c.rect((20, 32, 38, 54), BLUE, None, 4, 4)
    star = []
    for i in range(10):
        r = 15 if i % 2 == 0 else 6.5
        a = math.radians(-90 + i * 36)
        star.append((62 + r * math.cos(a), 44 + r * math.sin(a)))
    c.polygon(star, fill=ORANGE)


def level_name(c):
    """«Обновить имя уровня»: элементы на линии уровня, отметка уровня с
    оранжевой стрелкой к элементу — имя уровня прописывается элементам."""
    # Линии уровней (верхняя — пунктиром), с отметкой-треугольником справа.
    c.dashed((10, 30), (62, 30), BLUE, 3, 6, 4)
    c.line([(10, 70), (62, 70)], BLUE, 5)
    for y in (30, 70):
        c.polygon([(66, y - 9), (84, y - 9), (75, y)], fill=WHITE, outline=BLUE, w=3.5)
        c.line([(75, y), (75, y + 4)], BLUE, 3)
    c.polygon([(70, 61), (80, 61), (75, 66)], fill=ORANGE)
    # Элементы, стоящие на уровне.
    c.rect((14, 48, 30, 64), BLUE, WHITE, 4.5, 2)
    c.rect((38, 52, 52, 64), BLUE, WHITE, 4.5, 2)
    # Стрелка: имя уровня -> элемент.
    c.line([(75, 54), (75, 42), (22, 42), (22, 46)], ORANGE, 4)
    c.polygon([(16, 44), (28, 44), (22, 51)], fill=ORANGE)



def spell_check(c):
    """«Проверка орфографии»: надпись «Абв» с оранжевым волнистым
    подчёркиванием ошибки, строки текста и галочка исправления."""
    font = None
    for name in ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(name, 30 * K)
            break
        except IOError:
            continue
    if font is None:
        font = ImageFont.load_default()
    c.d.text((12 * K, 10 * K), u"Абв", font=font, fill=BLUE)
    # Волнистое подчёркивание под словом
    wave = [(12 + i * 1.5, 50 + 3 * math.sin(i * 1.5 / 4.0 * math.pi)) for i in range(41)]
    c.line(wave, ORANGE, 3.5)
    c.line([(12, 66), (46, 66)], BLUE, 5)
    c.line([(12, 80), (44, 80)], BLUE, 5)
    c.badge((70, 70), 17)
    c.line([(62, 70), (68, 77), (79, 63)], ORANGE, 5)


def crop_view(c):
    """«Обрезать вид»: план с рамкой подрезки, заданной двумя оранжевыми
    углами-точками; за рамкой — пунктир обрезанной части."""
    c.dashed((10, 30), (86, 30), BLUE, 3, 5, 4)
    c.dashed((30, 10), (30, 86), BLUE, 3, 5, 4)
    c.rect((22, 22, 74, 74), BLUE, WHITE, 5, 2)
    c.line([(32, 40), (64, 40)], BLUE, 4)
    c.line([(32, 54), (56, 54)], BLUE, 4)
    c.rect((40, 60, 64, 68), BLUE, None, 3, 1)
    for p in ((22, 22), (74, 74)):
        c.circle(p, 7, None, ORANGE)
        c.circle(p, 2.5, None, WHITE)


def fragment_explication(c):
    """«Экспликация фрагмента»: фрагмент плана в рамке подрезки (оранжевые
    углы) и таблица экспликации рядом."""
    c.rect((8, 14, 46, 52), BLUE, WHITE, 4, 2)
    c.line([(8, 34), (30, 34), (30, 14)], BLUE, 3)
    c.line([(30, 34), (30, 52)], BLUE, 3)
    for p in ((8, 14), (46, 52)):
        c.circle(p, 5, None, ORANGE)
    c.rect((34, 44, 88, 86), BLUE, WHITE, 4.5, 2)
    c.d.rectangle([34 * K, 44 * K, 88 * K, 54 * K], fill=BLUE)
    for y in (64, 75):
        c.line([(36, y), (86, y)], BLUE, 2.5)
    for x in (46, 76):
        c.line([(x, 54), (x, 86)], BLUE, 2.5)
    c.line([(50, 59), (70, 59)], ORANGE, 3)


def update_explication(c):
    """«Обновить экспликацию»: таблица экспликации и оранжевые стрелки
    обновления."""
    c.rect((8, 10, 62, 60), BLUE, WHITE, 4.5, 2)
    c.d.rectangle([8 * K, 10 * K, 62 * K, 20 * K], fill=BLUE)
    for y in (32, 46):
        c.line([(10, y), (60, y)], BLUE, 2.5)
    for x in (20, 50):
        c.line([(x, 20), (x, 60)], BLUE, 2.5)
    cx, cy, r = 66, 66, 18
    c.circle((cx, cy), r + 4, None, WHITE)
    box = [(cx - r) * K, (cy - r) * K, (cx + r) * K, (cy + r) * K]
    c.d.arc(box, 200, 340, fill=ORANGE, width=int(5 * K))
    c.d.arc(box, 20, 160, fill=ORANGE, width=int(5 * K))
    for ang, turn in ((340, 1), (160, 1)):
        a = math.radians(ang)
        tip = (cx + r * math.cos(a), cy + r * math.sin(a))
        t = (-math.sin(a), math.cos(a))
        c.polygon([(tip[0] + t[0] * 7, tip[1] + t[1] * 7),
                   (tip[0] - math.cos(a) * 6, tip[1] - math.sin(a) * 6),
                   (tip[0] + math.cos(a) * 6, tip[1] + math.sin(a) * 6)], fill=ORANGE)


def dwg_to_drafting(c):
    """«DWG → чертёжный»: пунктирная подложка, обводка сплошными линиями
    (оранжевым — обводимый сейчас отрезок) и перенесённая надпись «Аа»."""
    # Подложка DWG — пунктиром: контур помещения и перегородка.
    c.dashed((10, 12), (74, 12), BLUE, 3, 5, 4)
    c.dashed((74, 12), (74, 50), BLUE, 3, 5, 4)
    c.dashed((40, 12), (40, 40), BLUE, 3, 5, 4)
    # Уже обведено линиями детализации.
    c.line([(74, 12), (10, 12), (10, 62), (40, 62)], BLUE, 5)
    c.line([(40, 12), (40, 26)], ORANGE, 5)
    # Перенесённый текст.
    font = None
    for name in ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(name, 22 * K)
            break
        except IOError:
            continue
    if font is None:
        font = ImageFont.load_default()
    c.rect((44, 54, 88, 86), BLUE, WHITE, 4, 4)
    c.d.text((66 * K, 70 * K), u"Аа", font=font, fill=BLUE, anchor="mm")


def check_loi(c):
    """«Проверка LOI»: спецификация (шапка, строки, столбцы) с оранжевой
    пустой ячейкой и лупа над ней — проверка заполнения параметров."""
    c.rect((8, 10, 70, 74), BLUE, WHITE, 4.5, 2)
    c.d.rectangle([8 * K, 10 * K, 70 * K, 21 * K], fill=BLUE)
    for y in (34, 47, 60):
        c.line([(10, y), (68, y)], BLUE, 2.5)
    for x in (28, 49):
        c.line([(x, 21), (x, 74)], BLUE, 2.5)
    c.d.rectangle([50 * K, 35 * K, 67 * K, 46 * K], fill=PALE_ORANGE)
    c.line([(54, 40.5), (63, 40.5)], ORANGE, 3)
    c.magnifier((60, 58), 13, 14)
    c.line([(54, 58), (59, 63), (67, 53)], ORANGE, 4)


def align_view_range(c):
    """«Секущий диапазон»: вид сбоку на этаж — нижний уровень (сплошной),
    уровень выше (пунктир), между ними оранжевая секущая плоскость и
    скобка диапазона с отметками-треугольниками."""
    # Уровни: текущий — сплошной, следующий этаж — пунктир.
    c.dashed((10, 18), (70, 18), BLUE, 3, 6, 4)
    c.line([(10, 80), (70, 80)], BLUE, 5)
    for y in (18, 80):
        c.polygon([(72, y - 9), (88, y - 9), (80, y)], fill=WHITE, outline=BLUE, w=3.5)
    # Верх диапазона чуть ниже уровня выше, секущая плоскость — оранжевая.
    c.line([(18, 30), (62, 30)], BLUE, 3.5)
    c.line([(18, 52), (62, 52)], ORANGE, 5)
    c.polygon([(62, 45), (62, 59), (72, 52)], fill=ORANGE)
    # Скобка диапазона слева: от уровня до верха.
    c.line([(18, 30), (12, 30), (12, 80)], BLUE, 3.5)
    c.rect((26, 62, 40, 80), BLUE, WHITE, 4, 2)
    c.rect((46, 68, 58, 80), BLUE, WHITE, 4, 2)


def level_views(c):
    """«Виды по уровням»: три уровня (отметки-треугольники) и на каждом —
    свой план; оранжевые стрелки «уровень → вид»."""
    for y in (22, 48, 74):
        c.polygon([(8, y - 8), (22, y - 8), (15, y)], fill=WHITE, outline=BLUE, w=3)
        c.line([(15, y), (40, y)], BLUE, 3.5)
        c.line([(44, y), (52, y)], ORANGE, 4)
        c.polygon([(52, y - 5), (52, y + 5), (59, y)], fill=ORANGE)
        c.rect((62, y - 9, 88, y + 9), BLUE, WHITE, 3.5, 2)
        c.line([(75, y - 9), (75, y + 1)], BLUE, 2.5)
        c.line([(62, y + 1), (80, y + 1)], BLUE, 2.5)


def soue_floor(c):
    """План этажа (квартиры по сторонам коридора) с оповещателями в прихожих и коридоре."""
    c.rect((10, 14, 86, 82), BLUE, WHITE, 4, 2)
    c.line([(12, 40), (84, 40)], BLUE, 3.5)
    c.line([(12, 56), (84, 56)], BLUE, 3.5)
    for x in (35, 61):
        c.line([(x, 16), (x, 40)], BLUE, 3.5)
        c.line([(x, 56), (x, 80)], BLUE, 3.5)
    # оповещатели: на стенах квартир у коридора и по оси коридора
    for x in (22, 48, 74):
        c.polygon([(x - 5, 39), (x + 5, 39), (x + 3, 33), (x - 3, 33)], fill=ORANGE)
        c.polygon([(x - 5, 57), (x + 5, 57), (x + 3, 63), (x - 3, 63)], fill=ORANGE)
    for x in (30, 66):
        c.circle((x, 48), 4.5, None, ORANGE)


def fop_parameters(c):
    """«Параметры в ФОП»: файл параметров (строки-параметры, одна новая —
    оранжевая, с плюсом) и стрелка к категориям (три блока справа)."""
    c.polygon([(10, 10), (46, 10), (58, 22), (58, 86), (10, 86)], fill=WHITE,
              outline=BLUE, w=4.5)
    c.line([(46, 10), (46, 22), (58, 22)], BLUE, 3.5)
    for y in (32, 44, 56):
        c.line([(18, y), (48, y)], BLUE, 3.5)
    c.line([(22, 64), (22, 78)], ORANGE, 4.5)
    c.line([(15, 71), (29, 71)], ORANGE, 4.5)
    c.line([(35, 71), (50, 71)], ORANGE, 5)
    for y in (16, 40, 64):
        c.rect((70, y, 88, y + 16), BLUE, WHITE, 4, 3)
    c.rect((70, 64, 88, 80), ORANGE, PALE_ORANGE, 4, 3)
    c.line([(52, 72), (63, 72)], ORANGE, 4)
    c.polygon([(70, 72), (63, 66), (63, 78)], fill=ORANGE)


def rotate_3d_view(c):
    """«Повернуть 3D вид»: изометрический куб на вертикальной оси (пунктир)
    и оранжевая стрелка поворота вокруг неё."""
    c.dashed((48, 6), (48, 90), BLUE, 3, 5, 4)
    top = [(48, 26), (70, 37), (48, 48), (26, 37)]
    left = [(26, 37), (48, 48), (48, 72), (26, 61)]
    right = [(48, 48), (70, 37), (70, 61), (48, 72)]
    c.polygon(left, WHITE)
    c.polygon(right, PALE_ORANGE)
    c.polygon(top, WHITE)
    for face in (top, left, right):
        c.line(list(face) + [face[0]], BLUE, 4)
    box = [10 * K, 62 * K, 86 * K, 88 * K]
    c.d.arc(box, 200, 340, fill=ORANGE, width=int(5 * K))
    c.d.arc(box, 20, 140, fill=ORANGE, width=int(5 * K))
    a = math.radians(140)
    tip = (48 + 38 * math.cos(a), 75 + 13 * math.sin(a))
    c.polygon([(tip[0] - 9, tip[1] - 2), (tip[0] + 3, tip[1] - 7), (tip[0] + 2, tip[1] + 6)], ORANGE)


def greeting(c):
    """«Приветствие»: крупная буква «П» (начало «Привет») и оранжевый «!»
    на табличке — приветствие большими буквами."""
    c.rect((10, 14, 86, 82), BLUE, WHITE, 5, 12)
    c.line([(24, 68), (24, 28), (56, 28), (56, 68)], BLUE, 9)
    c.line([(72, 28), (72, 54)], ORANGE, 9)
    c.circle((72, 66), 5, None, ORANGE)


def detectors_to_slab(c):
    """«Извещатели на перекрытие»: перекрытие с перепадом отметки, под ним
    извещатель с оранжевой стрелкой вверх и отметка высоты от пола."""
    # перекрытие: слева ниже, справа выше (перепад)
    c.polygon([(8, 26), (46, 26), (46, 14), (88, 14), (88, 24), (54, 24), (54, 36), (8, 36)],
              fill=WHITE, outline=BLUE, w=4)
    # пол
    c.line([(8, 84), (88, 84)], BLUE, 5)
    # извещатель на низу перекрытия (правая часть) и стрелка подъёма
    c.polygon([(62, 25), (80, 25), (77, 33), (65, 33)], fill=ORANGE)
    c.line([(71, 66), (71, 44)], ORANGE, 5)
    c.polygon([(64, 46), (78, 46), (71, 37)], fill=ORANGE)
    # отметка высоты от пола слева: размерная линия и треугольник
    c.line([(22, 40), (22, 80)], BLUE, 3)
    c.polygon([(15, 40), (29, 40), (22, 47)], fill=BLUE)
    c.polygon([(15, 80), (29, 80), (22, 73)], fill=BLUE)
    c.line([(32, 60), (48, 60)], BLUE, 3)
    c.polygon([(32, 52), (44, 52), (38, 60)], fill=WHITE, outline=BLUE, w=2.5)


def detector_access(c):
    """«Доступ к извещателям»: разрез — под перекрытием извещатель, под ним
    воздуховод перекрывает зону доступа (пунктир от пола); стрелка переноса
    к извещателю на новом месте со свободной зоной."""
    # перекрытие и пол
    c.rect((6, 10, 90, 20), outline=BLUE, fill=WHITE, w=4, r=1)
    c.line([(8, 86), (88, 86)], BLUE, 5)
    # старое место: извещатель, зона доступа пунктиром, воздуховод поперёк
    c.polygon([(18, 20), (34, 20), (31, 27), (21, 27)], fill=BLUE)
    for x in (13, 39):
        c.dashed((x, 30), (x, 84), BLUE, w=3)
    c.rect((8, 38, 44, 52), outline=BLUE, fill=WHITE, w=4, r=2)
    c.line([(14, 41), (38, 49)], BLUE, 3)
    c.line([(14, 49), (38, 41)], BLUE, 3)
    # новое место: извещатель, свободная зона, стрелка переноса
    c.polygon([(62, 20), (78, 20), (75, 27), (65, 27)], fill=ORANGE)
    for x in (57, 83):
        c.dashed((x, 30), (x, 84), ORANGE, w=3)
    c.line([(30, 62), (60, 62)], ORANGE, 5)
    c.polygon([(58, 55), (58, 69), (68, 62)], fill=ORANGE)


def parking_marks(c):
    """«Отметки парковки»: план — машиноместо с буквой «P», рядом зона с
    оранжевой штриховкой, над ними высотные отметки (треугольник на полке)."""
    # зона: диагональная штриховка, обрезанная по прямоугольнику зоны
    c.rect((50, 40, 88, 88), outline=None, fill=WHITE, r=2)
    hatch = Image.new("RGBA", c.im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(hatch)
    for k in range(-40, 50, 9):
        draw.line([((50 + k) * K, 88 * K), ((98 + k) * K, 40 * K)], fill=ORANGE, width=int(2.5 * K))
    mask = Image.new("L", c.im.size, 0)
    ImageDraw.Draw(mask).rectangle([50 * K, 40 * K, 88 * K, 88 * K], fill=255)
    c.im.paste(hatch, (0, 0), Image.composite(hatch, Image.new("RGBA", c.im.size), mask))
    c.rect((50, 40, 88, 88), outline=BLUE, fill=None, w=4, r=2)
    # машиноместо: контур и «P»
    c.rect((8, 40, 42, 88), outline=BLUE, fill=WHITE, w=4, r=2)
    c.line([(20, 78), (20, 52), (28, 52)], BLUE, 5)
    c.d.arc([22 * K, 52 * K, 34 * K, 66 * K], 270, 90, fill=BLUE, width=int(5 * K))
    c.line([(20, 66), (28, 66)], BLUE, 5)
    # высотные отметки над машиноместом и зоной
    for x, shelf, color in ((25, 16, BLUE), (69, -16, ORANGE)):
        c.polygon([(x - 7, 22), (x + 7, 22), (x, 30)], fill=color)
        c.line([(x, 22), (x + shelf, 22)], BLUE, 3)
        c.line([(x, 30), (x, 36)], BLUE, 3)


def tag_trays(c):
    """«Марки лотков»: два параллельных лотка, марки стопкой над ними,
    выноски — вертикаль от края лотка и полка к марке."""
    for y0 in (54, 74):
        c.rect((6, y0, 90, y0 + 12), BLUE, WHITE, 4, 1)
        for x in range(16, 90, 12):
            c.line([(x, y0 + 2), (x, y0 + 10)], BLUE, 2)
    for (x, y_tray, y_shelf) in ((18, 74, 19), (32, 54, 39)):
        c.line([(x, y_tray), (x, y_shelf), (44, y_shelf)], ORANGE, 3)
        c.circle((x, y_tray), 3, None, ORANGE)
    for y in (11, 31):
        c.rect((44, y, 88, y + 16), None, BLUE, 0, 3)
        c.line([(50, y + 8), (80, y + 8)], WHITE, 3)


def compare_link_datums(c):
    """«Оси и уровни КФП»: оси с марками-кружками и уровень с отметкой
    (модель — синие), поверх — те же оси/уровень связи оранжевым пунктиром;
    одна ось связи смещена — расхождение."""
    # Уровень: модель — сплошной, связь — пунктир чуть выше.
    c.line([(8, 72), (70, 72)], BLUE, 4)
    c.dashed((8, 64), (70, 64), ORANGE, 3, 5, 3)
    c.polygon([(72, 63), (88, 63), (80, 72)], fill=WHITE, outline=BLUE, w=3.5)
    # Оси модели с марками.
    for x in (22, 50):
        c.line([(x, 28), (x, 86)], BLUE, 4)
        c.circle((x, 18), 10, BLUE, WHITE, 3.5)
    # Ось связи: первая совпадает, вторая сдвинута.
    c.dashed((22, 30), (22, 86), ORANGE, 3, 5, 3)
    c.dashed((58, 30), (58, 86), ORANGE, 3, 5, 3)
    c.line([(51, 46), (57, 46)], ORANGE, 3)


def tray_opening_boxes(c):
    """«Боксы на лотки»: стена в разрезе (штриховка), сквозь неё — лоток,
    вокруг лотка в стене — оранжевый бокс с запасом."""
    c.rect((38, 8, 58, 88), BLUE, WHITE, 4, 1)
    for y in range(14, 86, 10):
        c.line([(40, y + 6), (56, y - 2)], BLUE, 2)
    c.rect((32, 34, 64, 62), ORANGE, PALE_ORANGE, 4, 2)
    c.rect((6, 40, 90, 56), BLUE, WHITE, 4, 1)
    for x in range(14, 90, 10):
        if not 34 <= x <= 62:
            c.line([(x, 43), (x, 53)], BLUE, 2)


def _name_tag(c, box):
    """Оранжевая бирка с «текстом» (две строки-штриха) — записанное имя."""
    x0, y0, x1, y1 = box
    c.rect(box, ORANGE, PALE_ORANGE, 3.5, 4)
    c.line([(x0 + 6, y0 + 7), (x1 - 6, y0 + 7)], ORANGE, 3)
    c.line([(x0 + 6, y1 - 7), (x1 - 14, y1 - 7)], ORANGE, 3)


def write_load_name(c):
    """«Имя нагрузки»: панель, цепь к устройству, на цепи — бирка с именем."""
    c.rect((8, 54, 28, 84), BLUE, WHITE, 5, 3)
    c.line([(18, 54), (18, 40), (74, 40), (74, 58)], BLUE, 4)
    c.circle((74, 70), 12, BLUE, WHITE, 5)
    c.line([(46, 40), (46, 30)], ORANGE, 3)
    _name_tag(c, (26, 8, 70, 30))


def write_panel_name(c):
    """«Имя панели»: щит с дверцей, над ним — бирка с именем."""
    c.rect((22, 40, 74, 88), BLUE, WHITE, 5, 4)
    c.line([(48, 46), (48, 82)], BLUE, 3)
    c.circle((42, 64), 2.5, None, BLUE)
    c.circle((54, 64), 2.5, None, BLUE)
    _name_tag(c, (14, 8, 82, 32))
    c.line([(48, 32), (48, 40)], ORANGE, 3)


def language(c):
    """«Язык»: глобус — параллели и меридианы, один меридиан оранжевый."""
    cx, cy, r = 48, 48, 34
    c.circle((cx, cy), r, BLUE, WHITE, 5)
    c.line([(cx - r + 2, cy), (cx + r - 2, cy)], BLUE, 3.5)
    for dy in (-17, 17):
        half = math.sqrt(r * r - dy * dy) - 2
        c.line([(cx - half, cy + dy), (cx + half, cy + dy)], BLUE, 3)
    c.d.ellipse([(cx - 15) * K, (cy - r) * K, (cx + 15) * K, (cy + r) * K],
                outline=ORANGE, width=int(4 * K))
    c.line([(cx, cy - r + 2), (cx, cy + r - 2)], BLUE, 3)


ICONS = [
    ("_Themes.panel/LanguageSelector.combobox", language),
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
    ("Info.panel/Info.stack/Feedback.pushbutton", feedback),
    ("_Themes.panel/Actions.stack/Search.pushbutton", ribbon_search),
    ("_Themes.panel/Actions.stack/MyPanels.pushbutton", favorites),
    ("LOI.panel/UpdateLevelName.pushbutton", level_name),
    ("Tools.panel/SpellCheck.pushbutton", spell_check),
    ("Tools.panel/CropView.pushbutton", crop_view),
    ("Tools.panel/Rotate3DView.pushbutton", rotate_3d_view),
    ("Tools.panel/AlignViewRange.pushbutton", align_view_range),
    ("Tools.panel/LevelViews.pushbutton", level_views),
    ("ToolsRooms.panel/FragmentExplication.pushbutton", fragment_explication),
    ("ToolsRooms.panel/UpdateExplication.pushbutton", update_explication),
    ("Tools.panel/DwgToDrafting.pushbutton", dwg_to_drafting),
    ("LOI.panel/CheckLOI.pushbutton", check_loi),
    ("SOUE.panel/PlaceTypicalFloor.pushbutton", soue_floor),
    ("Tools.panel/FopParameters.pushbutton", fop_parameters),
    ("Tools.panel/Greeting.pushbutton", greeting),
    ("SPS.panel/DetectorsToSlab.pushbutton", detectors_to_slab),
    ("SPS.panel/DetectorAccess.pushbutton", detector_access),
    ("Tools.panel/ParkingMarks.pushbutton", parking_marks),
    ("Tools.panel/TagTrays.pushbutton", tag_trays),
    ("Tools.panel/CompareLinkDatums.pushbutton", compare_link_datums),
    ("Tools.panel/TrayOpeningBoxes.pushbutton", tray_opening_boxes),
    ("CircuitsGeneric.panel/WriteLoadName.pushbutton", write_load_name),
    ("CircuitsGeneric.panel/WritePanelName.pushbutton", write_panel_name),
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

# -*- coding: utf-8 -*-
"""
Чистая (без Revit API) часть кнопки «Точки доступа на двери»
(SKUD.panel/PlaceDoorAccessPoints): описание мест на мнемосхеме двери,
пересчёт места в точку относительно двери и раскладка состава группы
по местам. Работает на обычных dict/tuple, поэтому тестируется вне Revit
(tests/test_skud_door_layout.py).

Место (slot) — одна позиция на мнемосхеме: сторона двери (снаружи/внутри)
× роль устройства (считыватель, замок, ...). У места есть:
    families — имена СЕМЕЙСТВ (не типов), которые могут стоять на этом
               месте; тип берётся из выбранной для помещения группы;
    anchor   — от чего отсчитывается расстояние:
               "left"/"right" — от левого/правого края двери (как видит
               дверь человек, стоящий с этой стороны), расстояние
               откладывается ОТ проёма наружу;
               "top" — над дверью, расстояние по горизонтали — от оси
               двери вправо (минус — влево);
    offset_mm — расстояние по горизонтали (см. anchor);
    height_mm — высота от низа двери ("left"/"right") либо от верха
               двери ("top");
    depth_mm  — отступ от поверхности стены с этой стороны (0 — на стене,
               минус — в толщу стены/к полотну).
"""

import math

# (ключ, подпись, короткая метка на мнемосхеме, цвет маркера #RRGGBB)
ROLES = [
    ("reader", u"Считыватель", u"СЧ", "#2F6FB5"),
    ("lock", u"Замок", u"ЗМ", "#C0392B"),
    ("closer", u"Доводчик", u"ДВ", "#7D5BA6"),
    ("reed", u"Геркон", u"ГК", "#16A085"),
    ("emergency", u"Кнопка экстренной разблокировки", u"КЭР", "#E67E22"),
    ("intercom", u"Домофон", u"ДМ", "#2C3E50"),
    ("exit", u"Кнопка выхода", u"КВ", "#8E8E2F"),
]

SIDES = [
    ("outer", u"Снаружи"),
    ("inner", u"Внутри помещения"),
]

ANCHORS = [
    ("left", u"от левого края"),
    ("right", u"от правого края"),
    ("top", u"над дверью, от оси"),
]

ANCHOR_KEYS = [key for key, _label in ANCHORS]

# Разумное положение по умолчанию — только чтобы мнемосхема сразу была
# осмысленной; семейства по умолчанию пустые (это соглашения проекта).
_DEFAULT_POSITIONS = {
    ("outer", "reader"): ("right", 150, 1000, 0),
    ("outer", "lock"): ("top", 300, 0, 0),
    ("outer", "closer"): ("top", -300, 50, 0),
    ("outer", "reed"): ("top", 450, 0, 0),
    ("outer", "emergency"): ("right", 150, 1300, 0),
    ("outer", "intercom"): ("right", 150, 1450, 0),
    ("outer", "exit"): ("right", 150, 1150, 0),
    ("inner", "reader"): ("right", 150, 1000, 0),
    ("inner", "lock"): ("top", 300, 0, 0),
    ("inner", "closer"): ("top", -300, 50, 0),
    ("inner", "reed"): ("top", 450, 0, 0),
    ("inner", "emergency"): ("right", 150, 1300, 0),
    ("inner", "intercom"): ("right", 150, 1450, 0),
    ("inner", "exit"): ("right", 150, 1000, 0),
}


def slot_key(side, role):
    return u"{}_{}".format(side, role)


def all_slot_keys():
    """Ключи всех мест в порядке мнемосхемы: сначала снаружи, потом внутри."""
    return [slot_key(side, role) for side, _s in SIDES for role, _l, _sh, _c in ROLES]


def split_slot_key(key):
    side, _, role = key.partition("_")
    return side, role


def default_slot(side, role):
    anchor, offset, height, depth = _DEFAULT_POSITIONS.get((side, role), ("right", 150, 1000, 0))
    return {
        "families": [],
        "anchor": anchor,
        "offset_mm": u"{}".format(offset),
        "height_mm": u"{}".format(height),
        "depth_mm": u"{}".format(depth),
    }


def to_float(value, default=0.0):
    try:
        text = u"{}".format(value).strip().replace(u",", u".")
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def normalize_family_name(name):
    return (name or u"").strip().lower()


def slot_local_position(slot, door_width_mm, door_height_mm):
    """
    Положение места на лицевой стороне двери в мм: (u, z, depth), где
    u — по горизонтали от оси двери вправо (как видит человек, стоящий
    с этой стороны), z — от низа двери вверх, depth — от поверхности
    стены к наблюдателю.
    """
    anchor = slot.get("anchor") or "right"
    offset = to_float(slot.get("offset_mm"))
    height = to_float(slot.get("height_mm"))
    depth = to_float(slot.get("depth_mm"))
    half = door_width_mm / 2.0

    if anchor == "left":
        return (-(half + offset), height, depth)
    if anchor == "top":
        return (offset, door_height_mm + height, depth)
    return (half + offset, height, depth)


def viewer_right(normal):
    """
    Горизонтальный вектор «вправо» для человека, стоящего со стороны
    normal (normal смотрит от стены к нему) и глядящего на дверь:
    взгляд d = -normal, право = d × Z = (-ny, nx, 0).
    """
    nx, ny = normal[0], normal[1]
    length = math.hypot(nx, ny)
    if length < 1e-9:
        return (1.0, 0.0, 0.0)
    return (-ny / length, nx / length, 0.0)


def world_point(origin, normal, face_offset, local, units_per_mm):
    """
    Точка места в координатах модели. origin — низ двери по оси проёма
    (точка вставки двери), normal — горизонтальная нормаль стороны
    (единичная, от стены к наблюдателю), face_offset — расстояние от
    origin до поверхности стены с этой стороны вдоль normal (в единицах
    модели), local — результат slot_local_position (мм).
    """
    u, z, depth = local
    right = viewer_right(normal)
    along_normal = face_offset + depth * units_per_mm
    return (
        origin[0] + right[0] * u * units_per_mm + normal[0] * along_normal,
        origin[1] + right[1] * u * units_per_mm + normal[1] * along_normal,
        origin[2] + z * units_per_mm,
    )


def active_slots(slots):
    """[(key, slot)] мест с хотя бы одним семейством, в порядке мнемосхемы."""
    result = []
    for key in all_slot_keys():
        slot = slots.get(key)
        if slot and slot.get("families"):
            result.append((key, slot))
    return result


def match_members_to_slots(members, slots):
    """
    Раскладывает состав группы по местам мнемосхемы.

    members — список (family_name, payload) — элементы группы (payload —
    что угодно, обычно тип семейства). slots — [(key, slot)] (см.
    active_slots), порядок важен: каждый элемент уходит на ПЕРВОЕ ещё не
    занятое место, в списке семейств которого есть его семейство. Так
    два считывателя одного семейства в группе встают снаружи и внутри, а
    один — только снаружи (наружные места идут первыми).

    Возвращает (assigned, unmatched): assigned — [(key, slot, payload)],
    unmatched — [(family_name, payload)] элементов, которым места не
    нашлось (семейство не указано ни в одном месте или все его места уже
    заняты).
    """
    taken = set()
    assigned = []
    unmatched = []

    for family_name, payload in members:
        wanted = normalize_family_name(family_name)
        target = None
        for key, slot in slots:
            if key in taken:
                continue
            names = set(normalize_family_name(n) for n in slot.get("families") or [])
            if wanted in names:
                target = (key, slot)
                break
        if target is None:
            unmatched.append((family_name, payload))
            continue
        taken.add(target[0])
        assigned.append((target[0], target[1], payload))

    return assigned, unmatched

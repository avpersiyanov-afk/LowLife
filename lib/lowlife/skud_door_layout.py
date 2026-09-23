# -*- coding: utf-8 -*-
"""
Чистая (без Revit API) часть кнопки «Точки доступа на двери»
(SKUD.panel/PlaceDoorAccessPoints): описание мест на мнемосхеме двери,
пересчёт места в точку относительно двери и состав типа точки доступа
по местам. Работает на обычных dict/tuple, поэтому тестируется вне Revit
(tests/test_skud_door_layout.py).

Место (slot) — одна позиция на мнемосхеме: сторона двери (снаружи/внутри)
× роль устройства (считыватель, замок, ...). У места есть:
    families — имена СЕМЕЙСТВ (не типов), которые могут стоять на этом
               месте; конкретный типоразмер задаёт тип точки доступа
               (см. ниже);
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
               минус — в толщу стены/к полотну);
    count     — только у замка и геркона: 1 или 2 (двустворчатая дверь);
               второй элемент ставится зеркально относительно оси двери.

Тип точки доступа (access type) — именованный состав: {"name": ...,
"composition": {slot_key: {"family": ..., "type": ...}}} — какой
типоразмер стоит на каком месте. Место без записи в составе в этом типе
не используется.
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

# Роли, у которых на мнемосхеме есть «Количество» (двустворчатые двери).
COUNTABLE_ROLES = ("lock", "reed")
MAX_COUNT = 2

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
        "count": u"1",
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


def slot_count(key, slot):
    """Сколько элементов ставится на место: 1, у замка/геркона — до MAX_COUNT."""
    _side, role = split_slot_key(key)
    if role not in COUNTABLE_ROLES:
        return 1
    count = int(to_float(slot.get("count"), 1.0))
    return max(1, min(MAX_COUNT, count))


def slot_local_positions(key, slot, door_width_mm, door_height_mm):
    """
    Положения всех элементов места (см. slot_local_position): первый — по
    настройке, второй (count=2) — зеркально относительно оси двери.
    """
    first = slot_local_position(slot, door_width_mm, door_height_mm)
    positions = [first]
    if slot_count(key, slot) >= 2:
        positions.append((-first[0], first[1], first[2]))
    return positions


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


def composition_items(access_type, slots):
    """
    Состав типа точки доступа по местам мнемосхемы, в порядке мнемосхемы.

    Возвращает (items, stale): items — [(key, slot, family, type_name)]
    мест, где задан типоразмер и его семейство всё ещё разрешено на этом
    месте; stale — [(key, family, type_name)] записей состава, чьё
    семейство с места уже убрано (в расстановке не участвуют).
    """
    composition = (access_type or {}).get("composition") or {}
    items = []
    stale = []
    for key in all_slot_keys():
        entry = composition.get(key)
        if not entry or not entry.get("family") or not entry.get("type"):
            continue
        slot = slots.get(key) or {}
        allowed = set(normalize_family_name(n) for n in slot.get("families") or [])
        if normalize_family_name(entry["family"]) not in allowed:
            stale.append((key, entry["family"], entry["type"]))
            continue
        items.append((key, slot, entry["family"], entry["type"]))
    return items, stale


def find_access_type(access_types, name):
    for access_type in access_types or []:
        if access_type.get("name") == name:
            return access_type
    return None

# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «СС1-8Mile» (SS1.panel/SS1Easy) без Revit API —
покрыта тестами (tests/test_ss1_easy_core.py). Revit-часть — ss1_easy.py.

Все высоты/отметки — в одной системе координат (футы, как у Revit), какие
именно — решает вызывающий код.
"""

try:
    _text = unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3 (тесты)
    _text = str


def normalize(text):
    """Имя для сравнения: без пробелов по краям, без учёта регистра."""
    if text is None:
        return u""
    return _text(text).strip().lower()


def split_names(text):
    """«Коридор, Вестибюль; Холл» → [«Коридор», «Вестибюль», «Холл»]."""
    if not text:
        return []
    result = []
    for chunk in _text(text).replace(u";", u",").replace(u"\n", u",").split(u","):
        chunk = chunk.strip()
        if chunk:
            result.append(chunk)
    return result


def shaft_spans_level(shaft_min_z, shaft_max_z, level_z, tol):
    """
    Проходит ли шахта через уровень: низ шахты не выше отметки уровня (с
    допуском) и шахта поднимается над уровнем больше чем на допуск. Шахта,
    которая заканчивается ровно на уровне (верх = отметка), его не
    проходит — на этом уровне кроссы не ставятся.
    """
    return shaft_min_z - tol <= level_z and shaft_max_z > level_z + tol


def door_target_side(from_name, to_name, target_name, neighbor_names):
    """
    Какое из помещений двери — целевое («Прихожая»), если второе — одно из
    соседних («Коридор»/«Вестибюль»). Возвращает "from", "to" или None.
    """
    target = normalize(target_name)
    neighbors = set(normalize(n) for n in neighbor_names)
    if not target:
        return None
    if normalize(from_name) == target and normalize(to_name) in neighbors:
        return "from"
    if normalize(to_name) == target and normalize(from_name) in neighbors:
        return "to"
    return None


def lowest_room_per_lot(rooms):
    """
    Двухуровневые (дуплексные) квартиры: из целевых помещений с одним и тем
    же именем лота оставляет одно — с минимальной отметкой.

    rooms — [(room_key, lot, elevation)]; elevation может быть None.
    Возвращает (keep_keys, no_lot_keys):
      keep_keys   — множество ключей помещений, для которых ставится подвод;
      no_lot_keys — помещения с пустым именем лота: они не группируются
                    (подвод ставится в каждое), но о них нужно предупредить.
    """
    groups = {}
    keep = set()
    no_lot = []
    for key, lot, elevation in rooms:
        lot_norm = normalize(lot)
        if not lot_norm:
            keep.add(key)
            no_lot.append(key)
            continue
        groups.setdefault(lot_norm, []).append((key, elevation))

    for entries in groups.values():
        known = [entry for entry in entries if entry[1] is not None]
        if known:
            keep.add(min(known, key=lambda entry: entry[1])[0])
        else:
            keep.add(entries[0][0])

    return keep, no_lot


def match_level(z, levels, tol):
    """
    Ближайший к отметке z уровень из levels ([(уровень, отметка)]) в
    пределах допуска tol, иначе None.
    """
    best = None
    best_delta = None
    for level, elevation in levels:
        delta = abs(z - elevation)
        if delta <= tol and (best_delta is None or delta < best_delta):
            best = level
            best_delta = delta
    return best


def dedupe_key(x, y, level_key, grid=0.05):
    """Ключ места (X/Y с округлением ~15 мм + уровень) против двойных шахт."""
    return (int(round(x / grid)), int(round(y / grid)), level_key)


def filter_names(names, query):
    """
    Поиск по списку имён (семейств): без учёта регистра, каждое слово
    запроса должно встречаться в имени (в любом порядке). Пустой запрос —
    весь список. Порядок исходного списка сохраняется.
    """
    words = normalize(query).split()
    if not words:
        return list(names)
    return [name for name in names if all(word in normalize(name) for word in words)]

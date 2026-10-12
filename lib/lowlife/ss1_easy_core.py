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


def pick_shaft(x, y, section, shafts):
    """
    Шахта, от кросса которой строится цепь к подводу в точке (x, y).

    shafts — [(ключ, x, y, секция)] шахт СС того же уровня.
    section — секция помещения подвода; пусто — секция неизвестна.

    Если секция задана — ближайшая по плану шахта той же секции (без учёта
    регистра и пробелов по краям); такой нет — (None, "no_section").
    Если секции нет — ближайшая из всех, причина "no_room_section"
    (вызывающий код пишет предупреждение). Шахт нет — (None, "no_shafts").
    Возвращает (ключ или None, причина или None).
    """
    if not shafts:
        return None, "no_shafts"

    def nearest(candidates):
        return min(candidates, key=lambda s: (s[1] - x) ** 2 + (s[2] - y) ** 2)[0]

    wanted = normalize(section)
    if not wanted:
        return nearest(shafts), "no_room_section"
    same = [s for s in shafts if normalize(s[3]) == wanted]
    if not same:
        return None, "no_section"
    return nearest(same), None


def face_distance(offsets, sign, fallback, tol=1e-6):
    """
    Расстояние от точки двери до грани стены с нужной стороны.

    offsets  — смещения граней стены от точки двери вдоль FacingOrientation
               (со знаком; точка двери лежит на линии привязки стены, а она
               бывает и по оси, и по любой грани — поэтому половина толщины
               стены годится только как запасной вариант);
    sign     — +1 / -1: сторона (по FacingOrientation или против);
    fallback — что вернуть, если граней с этой стороны нет (половина
               толщины стены).
    Берётся самая дальняя грань с этой стороны (внешняя грань стены, а не
    граница слоя). Грань ровно в точке двери (смещение 0) годится для
    обеих сторон.
    """
    distances = [offset * sign for offset in offsets if offset * sign >= -tol]
    if not distances:
        return fallback
    return max(0.0, max(distances))


# Русские буквы, которые выглядят как латинские, — одна и та же буква маски,
# в какой бы раскладке её ни набрали («А.В.С» = «A.B.C»).
_LOOKALIKES = {
    u"А": u"A", u"В": u"B", u"С": u"C", u"Е": u"E", u"К": u"K", u"М": u"M",
    u"Н": u"H", u"О": u"O", u"Р": u"P", u"Т": u"T", u"Х": u"X",
}


def mask_letter(char):
    """Буква маски в одном написании (русская-двойник → латинская)."""
    return _LOOKALIKES.get(char, char)


def parse_letter_params(text):
    """
    Соответствия «буква маски = параметр» из строки настроек:
    «A=Этаж; B=Секция; C=Номер квартиры» (разделители пар — «;» или новая
    строка, внутри пары — «=» или «:»). Буква — один символ (регистр
    важен, русские буквы-двойники латинских считаются той же буквой).

    Возвращает ([(буква, параметр)] в порядке записи, [ошибки]). Пустой
    параметр — ошибка; повтор буквы — ошибка (берётся первое).
    """
    pairs = []
    errors = []
    seen = set()
    if not text:
        return pairs, errors
    for chunk in _text(text).replace(u"\n", u";").split(u";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        sep = None
        for candidate in (u"=", u":"):
            if candidate in chunk:
                sep = candidate
                break
        if sep is None:
            errors.append(u"«{}» — нужно «буква = параметр»".format(chunk))
            continue
        letter, param = chunk.split(sep, 1)
        letter = letter.strip()
        param = param.strip()
        if len(letter) != 1:
            errors.append(u"«{}» — слева должна быть одна буква".format(chunk))
            continue
        if not param:
            errors.append(u"«{}» — не указан параметр".format(chunk))
            continue
        key = mask_letter(letter)
        if key in seen:
            errors.append(u"буква «{}» указана дважды".format(letter))
            continue
        seen.add(key)
        pairs.append((key, param))
    return pairs, errors


def format_address(mask, values):
    """
    Маркировка по маске: каждая буква маски, для которой есть ключ в values
    (буквы — из parse_letter_params, русские двойники = латинские),
    заменяется значением; остальные символы маски остаются как есть
    («A.B.C» → «3.1.45»). Возвращает (текст, [буквы маски без значения]) —
    такая буква заменяется пустой строкой.
    """
    parts = []
    missing = []
    for char in mask or u"":
        letter = mask_letter(char)
        if letter not in values:
            parts.append(char)
            continue
        value = values.get(letter)
        value = u"" if value is None else _text(value).strip()
        if not value and letter not in missing:
            missing.append(letter)
        parts.append(value)
    return u"".join(parts), missing

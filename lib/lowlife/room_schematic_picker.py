# -*- coding: utf-8 -*-
"""
Выбор помещений/групп для кнопки Schematic.panel/BuildRoomSchematic
(«Рыба структурной схемы»).

Список помещений приходит от room_finder.get_records(doc) — та же база
(хост + все связи, с кэшем на сессию), что уже использует ToolsRooms.panel/
FindRoom. Уровни (порядок и подписи) — sot_levels.sorted_level_names/
get_level_label, та же сортировка этажей, что у СОТ/СПС/СКС.

Сценарий (v6):

  1. Параметр деления по СЕКЦИЯМ (один раз, опционально; закрыть диалог
     без выбора = пропустить шаг) — если у здания несколько секций, каждое
     значение параметра даёт свою отдельную схему (свой чертёжный вид, см.
     room_schematic.schematic_view_name). Без секций — один прогон.
  2. Для каждой секции — этажи ПО ПОРЯДКУ, один за другим, БЕЗ вопроса "на
     каком этаже": боксы обычно нужны на всех этажах подряд.

     На каждом этаже — ОДИН список ВСЕХ его помещений с чекбоксами
     (_manual_pick_boxes): отмечаете, что идёт на схему. Затем, если
     отмечено больше одного помещения — вопрос "объединить что-то из
     отмеченного в один бокс?" (forms.alert да/нет); при "да" — ещё один
     список с чекбоксами (уже только из отмеченного) на состав ОДНОЙ
     группы + название бокса (forms.ask_for_string), можно повторить для
     нескольких групп. Остальное, что не вошло ни в одну группу, — каждое
     помещение своим отдельным боксом.

     Типовые этажи: если этаж совпадает по расположению на плане (см.
     _xy_key) с предыдущим обработанным этажом настолько, что для его
     боксов нашлись соответствия среди помещений ЭТОГО этажа
     (_compute_suggested_boxes) — вместо списка сразу предлагается
     компактный выбор "Оставить как на предыдущем этаже" / "Выбрать
     заново" (не полный список с нуля каждый раз, если этаж такой же).
     То же самое — при возврате на уже пройденный этаж ("вернуться назад").

     После этажа — "Следующий этаж" (по умолчанию) / "Вернуться к другому
     этажу" (список всех этажей секции — поправить прошлый или перескочить
     вперёд) / "Завершить и построить".

Возвращает OrderedDict(section_label -> OrderedDict(level_name -> [box, ...])),
section_label=None, если деления по секциям не было (один-единственный
элемент словаря). None, если в итоге ничего не выбрано ни в одной секции.

ИСТОРИЯ (важно при дальнейшей правке — здесь нет живого Revit для проверки,
см. CLAUDE.md, поэтому ориентируйтесь на неё, а не угадывайте заново):
  - v3 показывала сразу один список с ПРЕДВАРИТЕЛЬНО отмеченными похожими
    помещениями через forms.TemplateListItem — в реальном Revit это
    вызывало пустой белый экран при нажатии "Сохранить". Убрано.
  - v5 использовала forms.CommandSwitchWindow почти на каждом шаге — после
    этого пользователь сообщил, что кнопка вообще ничего не строит (до
    финального алерта дело не доходило). forms.CommandSwitchWindow здесь
    БОЛЬШЕ НЕ ИСПОЛЬЗУЕТСЯ — подозревается как минимум ненадёжным в этом
    окружении, вместо неё везде обычный forms.SelectFromList (single-select
    список из строк вместо кнопок) — тот же самый API, что применяется по
    всему проекту без нареканий (см. ToolsRooms.panel/FindRoom и т.д.).
  - v6 (текущая) также заменила автоматическую группировку "по значению
    параметра" (нужно было сперва угадать/выбрать подходящий параметр) на
    ручную — пользователь сам отмечает чекбоксами, что объединить, это и
    проще для восприятия, и не зависит от того, заведён ли вообще в
    проекте подходящий параметр.
"""

from collections import OrderedDict

from pyrevit import forms

from lowlife.room_finder import natural_key
from lowlife.sot_levels import sorted_level_names, get_level_label

_NO_SECTIONS = u"(одна схема для всех, без секций)"

_NEXT = u"Следующий этаж"
_BACK = u"Вернуться к другому этажу"
_FINISH = u"Завершить и построить"

_KEEP = u"Оставить как на предыдущем этаже"
_REDO = u"Выбрать заново"

# Округление центра bbox помещения (футы) при сравнении "то же место на
# плане" между этажами (см. _xy_key) — типовые этажи в реальных моделях
# стыкуются не пиксель-в-пиксель, небольшой допуск нужен.
_XY_GRID_FT = 1.0


def list_room_param_names(records):
    """
    Отсортированный список имён параметров, встречающихся хотя бы на одном
    помещении из records — для выбора параметра деления на секции.
    Объединение (не пересечение): у части помещений (особенно из разных
    связей/типов) набор параметров может отличаться, показываем всё, что
    вообще где-то есть, а не только общее для всех сразу.
    """
    names = set()
    for record in records:
        try:
            for p in record.room.Parameters:
                name = p.Definition.Name if p and p.Definition else None
                if name:
                    names.add(name)
        except Exception:
            continue
    return sorted(names, key=lambda n: n.lower())


def _room_label(record):
    number = (record.number or u"").strip()
    name = (record.name or u"").strip()
    if number and name:
        return u"{} {}".format(number, name)
    return number or name or u"(без имени)"


def _xy_key(record):
    """
    Ключ "то же место на плане" — округлённый XY-центр bbox помещения
    (record.bbox уже в координатах ХОСТА и для связей — см. room_finder).
    None, если у помещения нет bbox (не должно случаться для размещённых
    помещений, но на всякий случай). Используется только для подсказки
    (подбор похожих боксов на новом этаже), поэтому округление достаточно
    грубое — не идентификатор, не для сохранения.
    """
    if not record.bbox:
        return None
    min_pt, max_pt = record.bbox
    cx = (min_pt.X + max_pt.X) / 2.0
    cy = (min_pt.Y + max_pt.Y) / 2.0
    return (round(cx / _XY_GRID_FT), round(cy / _XY_GRID_FT))


def _build_level_groups(records):
    """
    OrderedDict(level_name -> {"elements": [...], "level": Level|None,
    "order": int}) — форма, ожидаемая sot_levels.sorted_level_names.
    Level берётся с самого room (record.room.Level) — он резолвится Revit
    API на родном документе помещения (хост или связь), поэтому безопасен
    и для помещений из связи, в отличие от doc.GetElement(record.room.LevelId)
    на документе-хосте (см. sot_levels.group_elements_by_level — та функция
    для этого случая не подходит).
    """
    groups = OrderedDict()
    for index, record in enumerate(records):
        name = record.level_name or u"Без уровня"
        if name not in groups:
            level = None
            try:
                level = record.room.Level
            except Exception:
                level = None
            groups[name] = {"elements": [], "level": level, "order": index}
        groups[name]["elements"].append(record)
    return groups


def _split_into_sections(records, section_param):
    """OrderedDict(section_label -> [record, ...]). section_param=None ->
    {None: records} (одна секция, без разбиения). Иначе — по значению
    параметра, непустые значения в порядке появления, пустые/отсутствующие
    — одной группой "Без секции" в конце (не отбрасываются)."""
    if not section_param:
        return OrderedDict([(None, list(records))])

    from lowlife.params import get_param_any

    buckets = OrderedDict()
    empty_label = u"Без секции"
    for record in records:
        value = get_param_any(record.room, section_param)
        value = value.strip() if value else u""
        label = value or empty_label
        buckets.setdefault(label, []).append(record)

    ordered = OrderedDict()
    for label, recs in buckets.items():
        if label != empty_label:
            ordered[label] = recs
    if empty_label in buckets:
        ordered[empty_label] = buckets[empty_label]
    return ordered


class _LevelOption(object):
    def __init__(self, level_name, label):
        self.level_name = level_name
        self.label = label

    def __str__(self):
        return self.label


class _RoomEntry(object):
    """Один пункт списка выбора — отдельное помещение."""

    def __init__(self, record):
        self.record = record

    def __str__(self):
        return _room_label(self.record)

    def to_box(self):
        return {
            "kind": "room",
            "label": _room_label(self.record),
            "room_ids": [self.record.room_id] if self.record.room_id is not None else [],
        }


def _ask_section_param(records):
    param_names = list_room_param_names(records)
    choice = forms.SelectFromList.show(
        [_NO_SECTIONS] + param_names,
        title=u"Параметр деления на секции (если у здания несколько секций)",
        button_name=u"Выбрать",
        multiselect=False,
    )
    if not choice or choice == _NO_SECTIONS:
        return None
    return choice


def _ask_jump_to_level(level_order, boxes, section_label=None):
    """Список ВСЕХ этажей секции (с пометкой, где уже что-то добавлено) —
    только для явного "вернуться к другому этажу". Основной проход по
    этажам идёт по порядку сам, без этого диалога на каждом шаге."""
    prefix = u"[{}] ".format(section_label) if section_label else u""
    options = []
    for level_name in level_order:
        count = len(boxes.get(level_name, []))
        label = get_level_label(level_name)
        if count:
            label = u"{} (уже добавлено: {})".format(label, count)
        options.append(_LevelOption(level_name, label))

    picked = forms.SelectFromList.show(
        options,
        title=u"{}К какому этажу вернуться?".format(prefix),
        button_name=u"Перейти",
        multiselect=False,
    )
    return picked.level_name if picked else None


def _manual_pick_boxes(level_records, level_label, prefix):
    """
    Список ВСЕХ помещений этажа с чекбоксами -> из отмеченных, по желанию,
    ручная группировка (несколько раундов "отметьте, что объединить в один
    бокс" + название бокса) -> всё, что не вошло ни в одну группу, — каждое
    помещение своим отдельным боксом. Возвращает [box, ...] (может быть
    пустым, если ничего не отмечено/отменено).
    """
    entries = [_RoomEntry(r) for r in sorted(level_records, key=lambda r: natural_key(r.number))]

    picked = forms.SelectFromList.show(
        entries,
        title=u"{}{} — отметьте помещения для схемы".format(prefix, level_label),
        button_name=u"Далее",
        multiselect=True,
    )
    if not picked:
        return []

    remaining = list(picked)
    boxes = []

    while len(remaining) >= 2:
        combine = forms.alert(
            u"Объединить несколько из отмеченных помещений в один бокс (группу)?\n\n"
            u"Ещё не сгруппированы: {}".format(u", ".join(str(e) for e in remaining)),
            title=u"{}{} — группировка".format(prefix, level_label),
            yes=True, no=True,
        )
        if not combine:
            break

        group_entries = forms.SelectFromList.show(
            remaining,
            title=u"Какие помещения объединить в один бокс?",
            button_name=u"Объединить",
            multiselect=True,
        )
        if not group_entries or len(group_entries) < 2:
            forms.alert(u"Нужно отметить минимум два помещения для группы.",
                        title=u"Рыба структурной схемы")
            continue

        default_label = group_entries[0].record.name or u"Группа"
        label = forms.ask_for_string(
            default=default_label,
            prompt=u"Название бокса для этой группы:",
            title=u"Рыба структурной схемы",
        )
        if not label:
            continue

        room_ids = [e.record.room_id for e in group_entries if e.record.room_id is not None]
        boxes.append({"kind": "group", "label": label, "room_ids": room_ids})
        for e in group_entries:
            remaining.remove(e)

    for e in remaining:
        boxes.append(e.to_box())

    return boxes


def _compute_suggested_boxes(reference_boxes, level_records, records_by_id):
    """
    box-словари, подходящие для ТЕКУЩЕГО этажа (level_records) — перенос
    боксов reference_boxes (сохранённых на предыдущем обработанном этаже)
    туда, где на этом этаже нашлись помещения в тех же местах на плане
    (см. _xy_key). Группа переносится, если так совпадает большинство её
    помещений; одиночный бокс — только при полном совпадении (у него и
    так одно помещение). Пустой список, если общего не нашлось.
    """
    if not reference_boxes:
        return []

    current_by_xy = {}
    for record in level_records:
        key = _xy_key(record)
        if key is not None and key not in current_by_xy:
            current_by_xy[key] = record

    suggested = []
    for ref_box in reference_boxes:
        matched = []
        for rid in ref_box["room_ids"]:
            ref_record = records_by_id.get(rid)
            key = _xy_key(ref_record) if ref_record is not None else None
            if key is not None and key in current_by_xy:
                matched.append(current_by_xy[key])
        if not matched or not ref_box["room_ids"]:
            continue
        if (len(matched) / float(len(ref_box["room_ids"]))) < 0.5:
            continue
        suggested.append({
            "kind": ref_box["kind"],
            "label": ref_box["label"],
            "room_ids": [r.room_id for r in matched if r.room_id is not None],
        })

    return suggested


def _resolve_level_boxes(level_records, level_name, section_label, baseline):
    """
    Итоговый список box-словарей для этажа, либо None, если менять нечего
    (отмена — вызывающий код должен оставить boxes[level_name] как было).
    baseline — уже сохранённый для этого этажа набор (повторный заход) либо
    автоподбор по типовому этажу (см. _compute_suggested_boxes); пустой
    список/None, если сравнивать не с чем — тогда сразу обычный ручной выбор.
    """
    prefix = u"[{}] ".format(section_label) if section_label else u""
    level_label = get_level_label(level_name)

    if baseline:
        labels = u", ".join(b["label"] for b in baseline)
        choice = forms.SelectFromList.show(
            [_KEEP, _REDO],
            title=u"{}{}: похоже на другой этаж — {}".format(prefix, level_label, labels),
            button_name=u"Выбрать",
            multiselect=False,
        )
        if not choice:
            return None
        if choice == _KEEP:
            return list(baseline)

    return _manual_pick_boxes(level_records, level_label, prefix)


def _pick_section_boxes(section_records, records_by_id, section_label=None):
    """
    Проход по этажам ОДНОЙ секции (или всего проекта, если секций нет —
    section_label=None) — по порядку, без вопроса "на каком этаже": боксы
    обычно нужны на всех этажах подряд, поэтому после каждого этажа сразу
    идёт следующий. Возвращает OrderedDict(level_name -> [box, ...]).
    """
    level_groups = _build_level_groups(section_records)
    level_order = sorted_level_names(level_groups)

    boxes = OrderedDict()
    visited_levels = set()
    last_level_with_boxes = None
    prefix = u"[{}] ".format(section_label) if section_label else u""

    if not level_order:
        return boxes

    level_index = 0

    while True:
        level_name = level_order[level_index]
        level_records = level_groups[level_name]["elements"]
        existing_boxes = boxes.get(level_name, [])

        baseline = existing_boxes
        if not baseline and level_name not in visited_levels and last_level_with_boxes is not None:
            baseline = _compute_suggested_boxes(
                boxes.get(last_level_with_boxes, []), level_records, records_by_id
            )

        visited_levels.add(level_name)

        resolved = _resolve_level_boxes(level_records, level_name, section_label, baseline)
        if resolved is not None:
            boxes[level_name] = resolved

        if boxes.get(level_name):
            last_level_with_boxes = level_name

        is_last = level_index == len(level_order) - 1
        total_boxes = sum(len(v) for v in boxes.values())

        nav_options = ([_NEXT] if not is_last else []) + [_BACK, _FINISH]
        nav_choice = forms.SelectFromList.show(
            nav_options,
            title=u"{}Этаж «{}» готов. Боксов на нём: {} (всего боксов: {}). Что дальше?".format(
                prefix, get_level_label(level_name), len(boxes.get(level_name, [])), total_boxes
            ),
            button_name=u"Выбрать",
            multiselect=False,
        )

        if nav_choice == _BACK:
            jump_to = _ask_jump_to_level(level_order, boxes, section_label)
            if jump_to is not None:
                level_index = level_order.index(jump_to)
                continue
            if is_last:
                break
            nav_choice = _NEXT

        if nav_choice == _NEXT:
            level_index += 1
            continue

        break

    return boxes


def show(doc, records):
    """
    Ведёт пользователя через весь цикл выбора (секции — один раз, затем по
    каждой секции — этаж -> боксы на нём, см. _pick_section_boxes).
    Возвращает OrderedDict(section_label -> OrderedDict(level_name ->
    [box, ...])) — section_label=None, если секций не было (единственный
    элемент словаря). None, если в итоге ничего не выбрано ни в одной секции.
    """
    if not records:
        return None

    section_param = _ask_section_param(records)

    records_by_id = dict((r.room_id, r) for r in records if r.room_id is not None)
    sections = _split_into_sections(records, section_param)

    result = OrderedDict()
    for section_label, section_records in sections.items():
        boxes = _pick_section_boxes(section_records, records_by_id, section_label)
        if any(boxes.values()):
            result[section_label] = boxes

    return result if result else None

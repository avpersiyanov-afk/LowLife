# -*- coding: utf-8 -*-
"""
Выбор помещений/групп для кнопки Schematic.panel/BuildRoomSchematic
(«Рыба структурной схемы»).

Список помещений приходит от room_finder.get_records(doc) — та же база
(хост + все связи, с кэшем на сессию), что уже использует ToolsRooms.panel/
FindRoom. Уровни (порядок и подписи) — sot_levels.sorted_level_names/
get_level_label, та же сортировка этажей, что у СОТ/СПС/СКС.

Сценарий (v7):

  1. Четыре параметра, один раз, в этом порядке (закрыть диалог без выбора
     = использовать значение по умолчанию — см. _ask_param):
       а. параметр для ИМЕНИ помещения в маске (по умолчанию — встроенное
          "Имя");
       б. параметр для НОМЕРА помещения в маске (по умолчанию — встроенный
          "Номер"), маска = "Имя (Номер)" (см. _room_label);
       в. параметр для СЕКЦИИ — если у здания несколько секций, каждое
          значение даёт свою отдельную схему/вид (по умолчанию — без
          деления на секции, один прогон);
       г. параметр для ОБЩЕЙ ГРУППЫ — общее значение объединяет несколько
          помещений в один бокс схемы (по умолчанию — группы не строятся,
          только отдельные помещения).
  2. Для каждой секции — этажи ПО ПОРЯДКУ, один за другим (см.
     _pick_section_boxes): на этаже сначала список отдельных помещений
     (маска "Имя (Номер)"), затем список значений параметра общей группы,
     найденных на этом этаже (_floor_group_values) — на схеме этажа будут
     и то, и другое одновременно (независимо друг от друга).

     Типовые этажи/"довыбрать": то, что было выбрано (отдельные помещения
     — по совпадению ИМЕНИ, группы — по совпадению ЗНАЧЕНИЯ) на предыдущем
     обработанном этаже, переносится на новый этаж АВТОМАТИЧЕСКИ, без
     отдельного вопроса — списки на новом этаже показывают только то, что
     ЕЩЁ не перенесено (см. _pick_floor_boxes), чтобы можно было только
     ДОБАВИТЬ недостающее; отдельным вопросом да/нет предлагается убрать
     что-то из перенесённого, если этаж всё же отличается. То же самое —
     при возврате на уже пройденный этаж (см. "Вернуться к другому этажу").

     После этажа — "Следующий этаж" (по умолчанию) / "Вернуться к другому
     этажу" / "Завершить и построить".

  3. Когда все секции пройдены — имя чертёжного вида (forms.ask_for_string;
     для нескольких секций к нему добавляется "— <секция>", см.
     room_schematic.schematic_view_name).

Возвращает (view_base_name, OrderedDict(section_label ->
OrderedDict(level_name -> [box, ...]))), section_label=None, если деления
на секции не было. None, если в итоге ничего не выбрано ни в одной секции.

ИСТОРИЯ (важно при дальнейшей правке — здесь нет живого Revit для проверки,
см. CLAUDE.md, поэтому ориентируйтесь на неё, а не угадывайте заново):
  - Ранняя версия показывала список с ПРЕДВАРИТЕЛЬНО отмеченными похожими
    помещениями через forms.TemplateListItem — в реальном Revit это вызвало
    пустой белый экран при нажатии "Сохранить". Больше не используется.
  - Другая версия использовала forms.CommandSwitchWindow почти на каждом
    шаге — после этого пользователь сообщил, что кнопка вообще ничего не
    строит. forms.CommandSwitchWindow тоже больше не используется.
  - Единственные formsAPI, которыми пользуется этот файл сейчас —
    forms.SelectFromList (обычные объекты, без предотметок),
    forms.alert(yes=True, no=True) и forms.ask_for_string — у каждого есть
    рабочий прецедент в другом месте этого же проекта (см. ниже по коду).
    Не добавляйте сюда другие формы pyRevit без крайней необходимости.
"""

from collections import OrderedDict

from pyrevit import forms

from lowlife import room_finder
from lowlife.params import get_param_any
from lowlife.room_finder import natural_key
from lowlife.room_schematic import SCHEMATIC_VIEW_NAME
from lowlife.sot_levels import sorted_level_names, get_level_label

_NEXT = u"Следующий этаж"
_BACK = u"Вернуться к другому этажу"
_FINISH = u"Завершить и построить"


def list_room_param_names(records):
    """
    Отсортированный список имён параметров, встречающихся хотя бы на одном
    помещении из records — для всех четырёх диалогов выбора параметра.
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


def _ask_param(param_names, title):
    """Имя выбранного параметра, либо None (использовать значение по
    умолчанию) — как явным закрытием диалога, так и (защитно) отсутствием
    выбора. См. модульный докстринг про то, почему это не считается
    отменой всего сценария."""
    choice = forms.SelectFromList.show(
        param_names,
        title=u"{} (закройте окно без выбора, чтобы использовать значение по умолчанию)".format(title),
        button_name=u"Выбрать",
        multiselect=False,
    )
    return choice or None


def _name_value(record, name_param):
    """Имя помещения для маски — параметр из настроек, если задан и
    заполнен, иначе встроенное имя (record.name)."""
    if not name_param:
        return record.name
    value = get_param_any(record.room, name_param)
    return value.strip() if value else record.name


def _room_label(record, name_param, number_param):
    name = (_name_value(record, name_param) or u"").strip()
    number = (room_finder.number_value(record, number_param) or u"").strip()
    if name and number:
        return u"{} ({})".format(name, number)
    return name or number or u"(без имени)"


def _floor_group_values(level_records, group_param):
    """OrderedDict(value -> [record, ...]) — непустые значения group_param
    среди помещений ЭТОГО этажа, в порядке появления. {} если параметр
    общей группы не задан."""
    groups = OrderedDict()
    if not group_param:
        return groups
    for record in level_records:
        value = room_finder.type_value(record, group_param)
        if value:
            groups.setdefault(value, []).append(record)
    return groups


def _box_signature(box):
    return box["kind"], box["label"], tuple(sorted(box["room_ids"]))


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
    """Один пункт списка выбора — отдельное помещение как свой бокс."""

    def __init__(self, record, name_param, number_param):
        self.record = record
        self.name_param = name_param
        self.number_param = number_param

    def __str__(self):
        return _room_label(self.record, self.name_param, self.number_param)

    def to_box(self):
        return {
            "kind": "room",
            "label": _room_label(self.record, self.name_param, self.number_param),
            "room_ids": [self.record.room_id] if self.record.room_id is not None else [],
        }


class _GroupValueEntry(object):
    """Один пункт списка выбора — значение параметра общей группы, целиком
    как один будущий бокс схемы."""

    def __init__(self, value, records):
        self.value = value
        self.records = records

    def __str__(self):
        return u"▦ {} ({} пом.) — один бокс".format(self.value, len(self.records))

    def to_box(self):
        return {
            "kind": "group",
            "label": self.value,
            "room_ids": [r.room_id for r in self.records if r.room_id is not None],
        }


class _CarriedEntry(object):
    """Один пункт списка "что убрать из перенесённого" — оборачивает уже
    готовый box-словарь (перенесённый с предыдущего этажа), не запись
    помещения."""

    def __init__(self, box):
        self.box = box

    def __str__(self):
        kind_label = u"группа" if self.box["kind"] == "group" else u"помещение"
        return u"{}: {}".format(kind_label, self.box["label"])


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


def _compute_carry_over(reference_boxes, level_records, records_by_id, name_param, number_param, group_param):
    """
    box-словари, автоматически переносимые на этот этаж с предыдущего
    обработанного (reference_boxes) — отдельные помещения по совпадению
    ИМЕНИ (не номера — тот обычно на каждом этаже свой), группы по
    точному совпадению ЗНАЧЕНИЯ параметра общей группы. Пустой список,
    если сравнивать не с чем или совпадений не нашлось.
    """
    if not reference_boxes:
        return []

    current_by_name = {}
    for record in level_records:
        key = _name_value(record, name_param)
        if key and key not in current_by_name:
            current_by_name[key] = record

    current_group_values = _floor_group_values(level_records, group_param)

    carried = []
    for ref_box in reference_boxes:
        if ref_box["kind"] == "group":
            value = ref_box["label"]
            recs = current_group_values.get(value)
            if recs:
                carried.append({
                    "kind": "group",
                    "label": value,
                    "room_ids": [r.room_id for r in recs if r.room_id is not None],
                })
        else:
            ref_room_id = ref_box["room_ids"][0] if ref_box["room_ids"] else None
            ref_record = records_by_id.get(ref_room_id) if ref_room_id is not None else None
            if ref_record is None:
                continue
            match = current_by_name.get(_name_value(ref_record, name_param))
            if match is not None:
                carried.append({
                    "kind": "room",
                    "label": _room_label(match, name_param, number_param),
                    "room_ids": [match.room_id] if match.room_id is not None else [],
                })

    return carried


def _pick_floor_boxes(level_records, level_name, section_label, baseline, name_param, number_param, group_param):
    """
    Итоговый список box-словарей для этажа. baseline — то, что уже
    перенесено автоматически (типовой этаж) или сохранено раньше
    (повторный заход) — списки ниже показывают только то, что ЕЩЁ не в
    baseline (см. модульный докстринг), плюс отдельный вопрос про удаление
    чего-то из baseline, если он не пуст.
    """
    prefix = u"[{}] ".format(section_label) if section_label else u""
    level_label = get_level_label(level_name)

    baseline_room_ids = set()
    for b in baseline:
        baseline_room_ids.update(b["room_ids"])
    baseline_group_values = set(b["label"] for b in baseline if b["kind"] == "group")
    carried_labels = u", ".join(b["label"] for b in baseline)

    # --- отдельные помещения: что добавить ---
    remaining_records = [r for r in level_records if r.room_id not in baseline_room_ids]
    room_entries = [
        _RoomEntry(r, name_param, number_param)
        for r in sorted(remaining_records, key=lambda r: natural_key(room_finder.number_value(r, number_param)))
    ]

    added_rooms = []
    if room_entries:
        title = u"{}{} — отметьте помещения для схемы".format(prefix, level_label)
        if baseline:
            title = (
                u"{}{}: с предыдущего этажа уже перенесено — {}. "
                u"Отметьте, какие ЕЩЁ отдельные помещения добавить."
            ).format(prefix, level_label, carried_labels)
        picked = forms.SelectFromList.show(room_entries, title=title, button_name=u"Добавить", multiselect=True)
        if picked:
            added_rooms = [entry.to_box() for entry in picked]

    # --- группы: что добавить ---
    floor_groups = _floor_group_values(level_records, group_param)
    remaining_groups = OrderedDict(
        (value, recs) for value, recs in floor_groups.items() if value not in baseline_group_values
    )

    added_groups = []
    if remaining_groups:
        group_entries = [_GroupValueEntry(value, recs) for value, recs in remaining_groups.items()]
        picked = forms.SelectFromList.show(
            group_entries,
            title=u"{}{} — какие группы объединить в отдельный бокс".format(prefix, level_label),
            button_name=u"Добавить",
            multiselect=True,
        )
        if picked:
            added_groups = [entry.to_box() for entry in picked]

    # --- что убрать из перенесённого ---
    kept_baseline = list(baseline)
    if baseline:
        remove_something = forms.alert(
            u"{}{}: перенесено с предыдущего этажа — {}.\n\nУбрать что-то из этого списка?".format(
                prefix, level_label, carried_labels
            ),
            title=u"Рыба структурной схемы",
            yes=True, no=True,
        )
        if remove_something:
            remove_entries = [_CarriedEntry(b) for b in baseline]
            picked = forms.SelectFromList.show(
                remove_entries,
                title=u"{}{} — отметьте, что убрать".format(prefix, level_label),
                button_name=u"Убрать отмеченное",
                multiselect=True,
            )
            if picked:
                remove_signatures = set(_box_signature(entry.box) for entry in picked)
                kept_baseline = [b for b in baseline if _box_signature(b) not in remove_signatures]

    return kept_baseline + added_rooms + added_groups


def _pick_section_boxes(section_records, records_by_id, name_param, number_param, group_param, section_label=None):
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
            baseline = _compute_carry_over(
                boxes.get(last_level_with_boxes, []), level_records, records_by_id,
                name_param, number_param, group_param
            )

        visited_levels.add(level_name)

        boxes[level_name] = _pick_floor_boxes(
            level_records, level_name, section_label, baseline, name_param, number_param, group_param
        )

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
    Ведёт пользователя через весь сценарий (см. модульный докстринг).
    Возвращает (view_base_name, OrderedDict(section_label ->
    OrderedDict(level_name -> [box, ...]))), либо None, если в итоге
    ничего не выбрано ни в одной секции.
    """
    if not records:
        return None

    param_names = list_room_param_names(records)
    name_param = _ask_param(param_names, u"Параметр для имени помещения")
    number_param = _ask_param(param_names, u"Параметр для номера помещения")
    section_param = _ask_param(
        param_names, u"Параметр для номера секции (по нему будет несколько схем)"
    )
    group_param = _ask_param(
        param_names, u"Параметр для объединения нескольких помещений в общую группу"
    )

    records_by_id = dict((r.room_id, r) for r in records if r.room_id is not None)
    sections = _split_into_sections(records, section_param)

    result = OrderedDict()
    for section_label, section_records in sections.items():
        boxes = _pick_section_boxes(
            section_records, records_by_id, name_param, number_param, group_param, section_label
        )
        if any(boxes.values()):
            result[section_label] = boxes

    if not result:
        return None

    view_name = forms.ask_for_string(
        default=SCHEMATIC_VIEW_NAME,
        prompt=u"Имя чертёжного вида схемы"
               + (u" (для секций к нему добавится «— <секция>»)" if len(result) > 1 else u"") + u":",
        title=u"Рыба структурной схемы",
    )
    if not view_name:
        view_name = SCHEMATIC_VIEW_NAME

    return view_name, result

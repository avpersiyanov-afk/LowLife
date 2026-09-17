# -*- coding: utf-8 -*-
"""
Выбор помещений/групп для кнопки Schematic.panel/BuildRoomSchematic
(«Рыба структурной схемы»).

Список помещений приходит от room_finder.get_records(doc) — та же база
(хост + все связи, с кэшем на сессию), что уже использует ToolsRooms.panel/
FindRoom. Уровни (порядок и подписи) — sot_levels.sorted_level_names/
get_level_label, та же сортировка этажей, что у СОТ/СПС/СКС.

Сценарий (v3):

  1. Параметр деления по СЕКЦИЯМ (один раз, опционально) — если у здания
     несколько секций, каждое значение параметра даёт свою отдельную схему
     (свой чертёжный вид, см. room_schematic.schematic_view_name). Без
     секций — один прогон, как раньше.
  2. Параметр ГРУППИРОВКИ (один раз, общий на все секции) — общее значение
     объединяет несколько помещений в один бокс схемы (например «МОП»/
     «Квартира»); "(без группировки)" — доступны только отдельные помещения.
  3. Для каждой секции — цикл: выбор этажа -> на этом этаже ОДИН список с
     чекбоксами (multiselect), где вперемешку и группы (целиком), и ВСЕ
     помещения этажа по отдельности — можно отметить и группу, и вдобавок
     отдельные помещения из неё же (боксы независимы, специально не
     исключают друг друга).

     Типовые этажи: при ПЕРВОМ заходе на этаж (level ещё не посещался в
     этой секции) список приходит с уже отмеченными пунктами, похожими на
     то, что было выбрано на предыдущем обработанном этаже той же секции —
     сравнение "то же место на плане" по XY-центру bbox помещения (см.
     _xy_key), без привязки к номеру/имени (этажи могут перенумеровываться
     по-разному). Ничего нового выбирать не нужно, если этаж такой же —
     только снять лишнее/добавить то, что отличается.

     "Вернуться назад" — отдельной кнопки нет, устроено через тот же
     список этажей: выберите уже пройденный этаж ещё раз, список придёт с
     отмеченным ровно тем, что для него уже сохранено (см. existing_signatures
     в _build_entries_for_level) — снимите/добавьте нужное и сохраните
     заново, это ПОЛНОСТЬЮ заменит прежний выбор для этого этажа (а не
     добавится поверх — иначе снять ошибочно добавленное было бы нельзя).

     После сохранения выбора по этажу — переключатель "Выбрать ещё"/
     "Завершить и построить" (forms.CommandSwitchWindow).

Возвращает OrderedDict(section_label -> OrderedDict(level_name -> [box, ...])),
section_label=None, если деления по секциям не было (один-единственный
элемент словаря). None, если в итоге ничего не выбрано/отменено на любом
из первых двух шагов.

ВАЖНО (не проверено вживую, см. CLAUDE.md — в этом окружении нет Revit):
forms.TemplateListItem (предварительно отмеченные чекбоксы в multiselect-
списке) и forms.CommandSwitchWindow используются здесь ВПЕРВЫЕ в этом
репозитории — если предвыбор похожих помещений визуально не работает,
это первое, что стоит перепроверить (имя kwarg checked=/state=, и то, что
`.name` — то самое свойство, по которому pyRevit подписывает пункт списка).
"""

from collections import OrderedDict

from pyrevit import forms

from lowlife.params import get_param_any
from lowlife.room_finder import natural_key
from lowlife.sot_levels import sorted_level_names, get_level_label

_NO_GROUPING = u"(без группировки)"
_NO_SECTIONS = u"(одна схема для всех, без секций)"
_CONTINUE = u"Выбрать ещё"
_FINISH = u"Завершить и построить"

# Округление центра bbox помещения (футы) при сравнении "то же место на
# плане" между этажами (см. _xy_key) — типовые этажи в реальных моделях
# стыкуются не пиксель-в-пиксель, небольшой допуск нужен.
_XY_GRID_FT = 1.0


def list_room_param_names(records):
    """
    Отсортированный список имён параметров, встречающихся хотя бы на одном
    помещении из records — для выбора параметра группировки/секции.
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
    (предвыбор похожих помещений на новом этаже), поэтому округление
    достаточно грубое — не идентификатор, не для сохранения.
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


def _group_records_by_param(records, param_name):
    """OrderedDict(value -> [record, ...]) — только непустые значения
    param_name (в порядке первого появления). param_name=None -> {}
    (группировка выключена)."""
    groups = OrderedDict()
    if not param_name:
        return groups
    for record in records:
        value = get_param_any(record.room, param_name)
        value = value.strip() if value else u""
        if value:
            groups.setdefault(value, []).append(record)
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


class _GroupEntry(forms.TemplateListItem):
    """Один пункт списка выбора — целая группа помещений (общее значение
    параметра группировки) как один будущий бокс схемы."""

    def __init__(self, value, records, checked=False):
        forms.TemplateListItem.__init__(self, value, checked=checked)
        self.records = records
        self.state = checked

    @property
    def name(self):
        return u"▦ Группа «{}» ({} пом.) — один бокс".format(self.item, len(self.records))

    def __str__(self):
        return self.name

    def to_box(self):
        return {
            "kind": "group",
            "label": self.item,
            "room_ids": [r.room_id for r in self.records if r.room_id is not None],
        }


class _RoomEntry(forms.TemplateListItem):
    """Один пункт списка выбора — отдельное помещение как свой бокс.
    Показываются ВСЕ помещения этажа, включая те, что уже входят в одну
    из групп выше, — группа и отдельное помещение выбираются независимо
    (комбинированный сценарий: группа целиком + отдельные помещения)."""

    def __init__(self, record, checked=False):
        forms.TemplateListItem.__init__(self, record, checked=checked)
        self.state = checked

    @property
    def name(self):
        return _room_label(self.item)

    def __str__(self):
        return self.name

    def to_box(self):
        return {
            "kind": "room",
            "label": _room_label(self.item),
            "room_ids": [self.item.room_id] if self.item.room_id is not None else [],
        }


def _box_signature(box):
    return box["kind"], box["label"], tuple(sorted(box["room_ids"]))


def _build_entries_for_level(level_records, param_name, existing_signatures, reference_xy_keys):
    """
    entries для одного этажа — группы (значения param_name), затем все
    помещения по отдельности. Пункт приходит предварительно отмеченным,
    если: (а) он уже сохранён для этого этажа раньше (existing_signatures
    — точное совпадение sig, см. _box_signature — работает и для "вернуться
    и довыбрать"), либо (б) reference_xy_keys задан (первый заход на этот
    этаж в этой секции — см. _pick_section_boxes) и помещение/большинство
    помещений группы совпадают по месту на плане с предыдущим обработанным
    этажом (типовые этажи).
    """
    groups = _group_records_by_param(level_records, param_name)
    entries = []

    for value, recs in groups.items():
        sig = _box_signature({"kind": "group", "label": value,
                               "room_ids": [r.room_id for r in recs if r.room_id is not None]})
        checked = sig in existing_signatures
        if not checked and reference_xy_keys is not None and recs:
            matched = sum(1 for r in recs if _xy_key(r) in reference_xy_keys)
            checked = (matched / float(len(recs))) >= 0.5
        entries.append(_GroupEntry(value, recs, checked=checked))

    ordered_records = sorted(level_records, key=lambda r: natural_key(r.number))
    for record in ordered_records:
        sig = _box_signature({"kind": "room", "label": _room_label(record),
                               "room_ids": [record.room_id] if record.room_id is not None else []})
        checked = sig in existing_signatures
        if not checked and reference_xy_keys is not None:
            checked = _xy_key(record) in reference_xy_keys
        entries.append(_RoomEntry(record, checked=checked))

    return entries


def _ask_choice_param(records, title, none_label):
    param_names = list_room_param_names(records)
    choice = forms.SelectFromList.show(
        [none_label] + param_names,
        title=title,
        button_name=u"Выбрать",
        multiselect=False,
    )
    if not choice:
        return None, False
    return (None if choice == none_label else choice), True


def _ask_section_param(records):
    return _ask_choice_param(
        records, u"Параметр деления на секции (если у здания несколько секций)", _NO_SECTIONS
    )


def _ask_group_param(records):
    return _ask_choice_param(
        records, u"Параметр группировки помещений в боксы схемы", _NO_GROUPING
    )


def _ask_level(level_order, boxes, section_label=None):
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
        title=u"{}На каком этаже добавляем боксы?".format(prefix),
        button_name=u"Далее",
        multiselect=False,
    )
    return picked.level_name if picked else None


def _pick_section_boxes(section_records, param_name, records_by_id, section_label=None):
    """
    Цикл выбора этаж -> боксы для ОДНОЙ секции (или для всего проекта,
    если секций нет — section_label=None). Возвращает OrderedDict
    (level_name -> [box, ...]), может быть пустым, если пользователь сразу
    отменил выбор этажа.
    """
    level_groups = _build_level_groups(section_records)
    level_order = sorted_level_names(level_groups)

    boxes = OrderedDict()
    visited_levels = set()
    last_level_with_boxes = None

    while True:
        level_name = _ask_level(level_order, boxes, section_label)
        if level_name is None:
            break

        level_records = level_groups[level_name]["elements"]
        existing_boxes = boxes.get(level_name, [])
        existing_signatures = set(_box_signature(b) for b in existing_boxes)

        reference_xy_keys = None
        if level_name not in visited_levels and last_level_with_boxes is not None:
            reference_ids = set()
            for b in boxes.get(last_level_with_boxes, []):
                reference_ids.update(b["room_ids"])
            reference_xy_keys = set()
            for rid in reference_ids:
                ref_record = records_by_id.get(rid)
                key = _xy_key(ref_record) if ref_record is not None else None
                if key is not None:
                    reference_xy_keys.add(key)

        entries = _build_entries_for_level(level_records, param_name, existing_signatures, reference_xy_keys)

        hint = u""
        if reference_xy_keys:
            hint = u" Похожие на этаж «{}» помещения уже отмечены — снимите лишнее, добавьте недостающее.".format(
                get_level_label(last_level_with_boxes)
            )

        picked = forms.SelectFromList.show(
            entries,
            title=u"{}{} — отметьте группы и/или отдельные помещения.{}".format(
                u"[{}] ".format(section_label) if section_label else u"",
                get_level_label(level_name), hint
            ),
            button_name=u"Сохранить выбор для этажа",
            multiselect=True,
        )

        visited_levels.add(level_name)

        if picked:
            # Полная замена, не добавление поверх — иначе снять ошибочно
            # сохранённый ранее бокс при повторном заходе было бы нельзя
            # (см. модульный докстринг, "вернуться назад и довыбрать").
            boxes[level_name] = [entry.to_box() for entry in picked]
            if boxes[level_name]:
                last_level_with_boxes = level_name
        elif existing_boxes:
            # Пусто вернулось из-за Esc/крестика — трактуем как "без
            # изменений", а не как "очистить этаж" (см. докстринг show):
            # pyRevit не различает "ОК с пустым списком" и "отмена".
            last_level_with_boxes = level_name

        total_boxes = sum(len(v) for v in boxes.values())
        if total_boxes == 0:
            continue

        switch = forms.CommandSwitchWindow.show(
            [_CONTINUE, _FINISH],
            message=u"{}Добавлено боксов: {} (этажей: {}).".format(
                u"[{}] ".format(section_label) if section_label else u"",
                total_boxes, len([1 for v in boxes.values() if v])
            ),
        )
        if switch != _CONTINUE:
            break

    return boxes


def show(doc, records):
    """
    Ведёт пользователя через весь цикл выбора (секции и параметр
    группировки — один раз, затем по каждой секции — этаж -> боксы на нём,
    см. _pick_section_boxes). Возвращает OrderedDict(section_label ->
    OrderedDict(level_name -> [box, ...])) — section_label=None, если
    секций не было (единственный элемент словаря). None, если пользователь
    отменил выбор на любом из первых двух шагов, либо в итоге ничего не
    выбрано ни в одной секции.
    """
    if not records:
        return None

    section_param, section_chosen = _ask_section_param(records)
    if not section_chosen:
        return None

    group_param, group_chosen = _ask_group_param(records)
    if not group_chosen:
        return None

    records_by_id = dict((r.room_id, r) for r in records if r.room_id is not None)
    sections = _split_into_sections(records, section_param)

    result = OrderedDict()
    for section_label, section_records in sections.items():
        boxes = _pick_section_boxes(section_records, group_param, records_by_id, section_label)
        if any(boxes.values()):
            result[section_label] = boxes

    return result if result else None

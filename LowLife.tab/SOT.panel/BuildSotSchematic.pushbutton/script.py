# -*- coding: utf-8 -*-
__title__ = u"Структурная\nсхема"
__doc__ = (
    u"Строит/обновляет структурную схему СОТ (охранное телевидение). Сама "
    u"находит на модели все устройства, тип которых сопоставлен категории в "
    u"настройках СОТ, группирует их по этажу (подпись — «Этаж N (отметка)», "
    u"порядок по отметке: отрицательные — внизу схемы, глубже — ниже; "
    u"положительные — выше, чем больше отметка) и по помещению.\n\n"
    u"Повторный запуск не пересоздаёт схему с нуля: обновляется вид с именем "
    u"из настроек СОТ (создаётся с этим именем, если его ещё нет), раскладка "
    u"предыдущего запуска хранится в служебном параметре этого вида — "
    u"обновляются только этаж/помещение/устройство, где реально что-то "
    u"изменилось (добавилось/пропало/переехало), остальное остаётся как было, "
    u"теми же элементами. Соседи справа/ниже места изменения сдвигаются, "
    u"чтобы закрыть/освободить место. Шаблон вида (если выбран в настройках) "
    u"применяется на каждом запуске.\n\n"
    u"Корпуса и секции: если в настройках заданы параметр корпуса и/или "
    u"параметр секции — схема делится на блоки «Корпус → Секция» (друг под "
    u"другом, по порядку корпусов, внутри корпуса — по порядку секций). У "
    u"каждого блока свой заголовок («Корпус 1, секция 2»), свои этажи, свой "
    u"стояк и свой шкаф. Если задано ещё и значение корпуса для фильтрации — "
    u"на схеме только этот корпус (его секции — по-прежнему отдельными "
    u"блоками); так можно вести отдельный вид на каждый корпус.\n\n"
    u"Если в настройках задана категория «Шкаф» — рисуются линии до него "
    u"шинной топологией: на каждом этаже один общий горизонтальный "
    u"коллектор чуть ниже узлов, от каждого узла к нему короткий "
    u"вертикальный отвод, коллекторы этажей секции выходят на вертикальный "
    u"стояк этой секции слева от рамок этажей. Эти линии не редактируются "
    u"вручную — на каждом запуске перерисовываются заново по актуальным "
    u"позициям.\n\n"
    u"Shift+клик — настройки этой кнопки."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    ElementId, FilteredElementCollector, BuiltInCategory, ViewFamilyType, ViewFamily, ViewDrafting
)
from pyrevit import revit, forms, script as pyrevit_script, EXEC_PARAMS

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict

from lowlife.params import get_string_param, set_param_any
from lowlife.skud import category_by_type_id
from lowlife import sot_settings
from lowlife.sot_settings import (
    get_settings_silent, get_settings_interactive, get_schematic_category_symbols,
    get_schematic_category_device_type_ids, get_node_annotation_symbol, get_view_template,
    SOURCE_CATEGORIES
)
from lowlife.sot_levels import group_elements_by_level, sorted_level_names, get_level_label
from lowlife.sot_schematic import (
    sync_section_groups, sync_cable_connections, previous_section_groups, delete_elements
)
from lowlife.sot_sections import split_into_groups, natural_sort_key, normalize_value, NO_BUILDING
from lowlife.sot_layout_state import find_layout_view, save_state
from lowlife.room_info import get_point as get_room_point, find_room_value

doc = revit.doc
output = pyrevit_script.get_output()


def _open_settings():
    edited = get_settings_interactive(doc)
    forms.alert(
        u"Отменено, настройки не изменены." if edited is None
        else u"Настройки сохранены."
    )


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    _open_settings()
    pyrevit_script.exit()


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

sot_settings.require(settings, [
    "room_param_name", "room_mask", "address_param_name",
    "node_label_offset_mm", "schematic_view_name", "layout_param_name", "device_uid_param_name",
    "schematic_device_categories_text"
])

LEVEL_PARAM_NAME = settings["level_param_name"]
ROOM_PARAM_NAME = settings["room_param_name"]
ROOM_MASK = settings["room_mask"]
ADDRESS_PARAM_NAME = settings["address_param_name"]
BUILDING_PARAM_NAME = (settings.get("building_param_name") or u"").strip()
SECTION_PARAM_NAME = (settings.get("section_param_name") or u"").strip()
BUILDING_FILTER_VALUE = settings["building_filter_value"].strip()
SCHEMATIC_VIEW_NAME = settings["schematic_view_name"]
LAYOUT_PARAM_NAME = settings["layout_param_name"]
DEVICE_UID_PARAM_NAME = settings["device_uid_param_name"]
CABINET_CATEGORY_NAME = settings["cabinet_category_name"].strip()

try:
    NODE_LABEL_OFFSET_MM = float(settings["node_label_offset_mm"].replace(u",", u"."))
except (ValueError, AttributeError):
    NODE_LABEL_OFFSET_MM = 5.0

try:
    MAX_ROW_WIDTH_MM = float((settings.get("max_row_width_mm") or u"").replace(u",", u".") or 0.0)
except (ValueError, AttributeError):
    MAX_ROW_WIDTH_MM = 0.0
if MAX_ROW_WIDTH_MM < 0.0:
    MAX_ROW_WIDTH_MM = 0.0

ANNOTATION_SYMBOL = get_node_annotation_symbol(doc, settings)
VIEW_TEMPLATE = get_view_template(doc, settings)

if ANNOTATION_SYMBOL is None:
    forms.alert(
        u"Не выбрана марка узла в настройках СОТ — марки над схемными "
        u"семействами ставиться не будут.\n\n"
        u"Откройте «Параметры СОТ» и выберите марку узла, чтобы включить их."
    )

CATEGORY_SYMBOLS = get_schematic_category_symbols(doc, settings)

if not CATEGORY_SYMBOLS:
    forms.alert(
        u"Не выбран ни один тип схемного семейства для категорий устройств СОТ.\n\n"
        u"Откройте «Параметры СОТ», обновите список категорий и выберите "
        u"схемное семейство для каждой из них.",
        exitscript=True
    )

CATEGORY_DEVICE_TYPE_IDS = get_schematic_category_device_type_ids(settings)

if not CATEGORY_DEVICE_TYPE_IDS:
    forms.alert(
        u"Не выбраны реальные типы устройств ни для одной категории СОТ.\n\n"
        u"Откройте «Параметры СОТ» и выберите типы устройств модели для "
        u"каждой категории.",
        exitscript=True
    )


def category_for_device(el):
    return category_by_type_id(el, CATEGORY_DEVICE_TYPE_IDS)


# ------------------------------------------------------------
# АВТОСБОР УСТРОЙСТВ
# ------------------------------------------------------------

all_mapped_type_ids = set()
for ids in CATEGORY_DEVICE_TYPE_IDS.values():
    all_mapped_type_ids |= ids

elements = []

for cat_key in SOURCE_CATEGORIES:
    collected = FilteredElementCollector(doc) \
        .OfCategory(getattr(BuiltInCategory, cat_key)) \
        .WhereElementIsNotElementType() \
        .ToElements()

    for el in collected:
        try:
            type_id = el.GetTypeId().IntegerValue
        except:
            continue
        if type_id in all_mapped_type_ids:
            elements.append(el)

if not elements:
    forms.alert(
        u"Не найдено ни одного устройства с типом, сопоставленным категории "
        u"в настройках СОТ.",
        exitscript=True
    )


# ------------------------------------------------------------
# ФИЛЬТР ПО КОРПУСУ (оба поля заданы в настройках — без диалога)
# ------------------------------------------------------------

def _raw_param(el, param_name):
    """Значение параметра корпуса/секции; None — параметр не задан в настройках."""
    if not param_name:
        return None
    return get_string_param(el, param_name) or u""


if BUILDING_PARAM_NAME and BUILDING_FILTER_VALUE:
    elements = [
        el for el in elements
        if normalize_value(_raw_param(el, BUILDING_PARAM_NAME), NO_BUILDING) == BUILDING_FILTER_VALUE
    ]

    if not elements:
        forms.alert(
            u"После фильтрации по корпусу «{}» не осталось устройств.\n\n"
            u"Проверьте значение в настройках СОТ — «Значение корпуса для "
            u"фильтрации».".format(BUILDING_FILTER_VALUE),
            exitscript=True
        )


# ------------------------------------------------------------
# БЛОКИ «КОРПУС → СЕКЦИЯ» (без параметров — один блок, как раньше)
# ------------------------------------------------------------

section_groups = split_into_groups(
    elements,
    lambda el: _raw_param(el, BUILDING_PARAM_NAME),
    lambda el: _raw_param(el, SECTION_PARAM_NAME)
)


# ------------------------------------------------------------
# ШКАФ — свой в каждом блоке; линии от остальных узлов блока к нему
# (см. sync_cable_connections)
# ------------------------------------------------------------

cabinet_uid_by_group = {}
cabinet_extra_by_group = {}

if CABINET_CATEGORY_NAME:
    for group in section_groups:
        cabinet_elements = [el for el in group["items"] if category_for_device(el) == CABINET_CATEGORY_NAME]

        if cabinet_elements:
            cabinet_elements.sort(key=lambda el: natural_sort_key(get_string_param(el, ADDRESS_PARAM_NAME) or u""))
            cabinet_uid_by_group[group["key"]] = cabinet_elements[0].UniqueId
            if len(cabinet_elements) > 1:
                cabinet_extra_by_group[group["key"]] = len(cabinet_elements) - 1


# ------------------------------------------------------------
# ГРУППИРОВКА ПО ЭТАЖУ (внутри каждого блока)
# ------------------------------------------------------------

for group in section_groups:
    group["level_groups"] = group_elements_by_level(doc, group["items"], LEVEL_PARAM_NAME)
    group["level_order"] = sorted_level_names(group["level_groups"])
    group["level_labels"] = dict((name, get_level_label(name)) for name in group["level_order"])


def resolve_room_value(doc, el, counters):
    """
    Значение параметра ROOM_PARAM_NAME на устройстве, если оно уже
    заполнено (например, кнопкой «Запись номера помещения»); если пусто — ищет
    помещение в связанной модели сам (как это делал исходный Dynamo-скрипт)
    и записывает найденное значение на устройство, чтобы при повторном
    запуске схемы и других кнопках оно уже было под рукой.
    """
    room_value = get_string_param(el, ROOM_PARAM_NAME)

    if room_value and room_value.strip():
        counters["already_set"] += 1
        return room_value.strip()

    point = get_room_point(el)
    looked_up_value = find_room_value(doc, point, ROOM_MASK)

    if looked_up_value:
        set_param_any(el, ROOM_PARAM_NAME, looked_up_value)
        counters["looked_up"] += 1
        return looked_up_value

    counters["not_found"] += 1
    return u""


# ------------------------------------------------------------
# ЧЕРТЁЖНЫЙ ВИД: ищем вид с именем из настроек (для обновления), иначе создаём
# ------------------------------------------------------------

view, previous_state, name_conflict = find_layout_view(doc, SCHEMATIC_VIEW_NAME, LAYOUT_PARAM_NAME)

if name_conflict:
    forms.alert(
        u"В проекте уже есть вид с именем «{}», но это не чертёжный вид — "
        u"структурную схему СОТ туда поставить нельзя.\n\n"
        u"Переименуйте существующий вид либо измените имя вида в «Параметры "
        u"СОТ».".format(SCHEMATIC_VIEW_NAME),
        exitscript=True
    )

is_new_view = view is None

if is_new_view:
    drafting_type_id = None

    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements():
        try:
            if vft.ViewFamily == ViewFamily.Drafting:
                drafting_type_id = vft.Id
                break
        except:
            continue

    if drafting_type_id is None:
        forms.alert(u"В проекте не найден ViewFamilyType для чертёжных видов (Drafting).", exitscript=True)

    previous_state = {"v": 1, "levels": {}}


# ------------------------------------------------------------
# СИНХРОНИЗАЦИЯ
# ------------------------------------------------------------

unmatched_report = []
room_counters = {"already_set": 0, "looked_up": 0, "not_found": 0}
sync_stats = {}

with revit.Transaction(u"Sync SOT Schematic"):
    for group in section_groups:
        level_room_groups = OrderedDict()

        for level_name in group["level_order"]:
            room_groups = OrderedDict()

            for el in group["level_groups"][level_name]["elements"]:
                room_value = resolve_room_value(doc, el, room_counters)
                room_key = room_value if room_value else u"(пусто)"

                if room_key not in room_groups:
                    room_groups[room_key] = []
                room_groups[room_key].append(el)

            level_room_groups[level_name] = room_groups

        group["level_room_groups"] = level_room_groups

    if is_new_view:
        view = ViewDrafting.Create(doc, drafting_type_id)
        view.Name = SCHEMATIC_VIEW_NAME
        view.Scale = 1

    view_name = view.Name

    try:
        view.ViewTemplateId = VIEW_TEMPLATE.Id if VIEW_TEMPLATE is not None else ElementId.InvalidElementId
    except:
        pass

    # Старые линии к шкафу удаляются до синхронизации блоков: блок мог
    # пропасть целиком, а его линии лежат в общем списке раскладки.
    old_cable_line_ids = list(previous_state.get("cable_line_ids", []))
    for prev_group in previous_section_groups(previous_state).values():
        old_cable_line_ids.extend(prev_group.get("cable_line_ids", []))
    delete_elements(doc, old_cable_line_ids)

    new_state, all_report_rows = sync_section_groups(
        doc, view, section_groups, previous_state, unmatched_report, sync_stats,
        category_symbols=CATEGORY_SYMBOLS, category_for_device=category_for_device,
        room_param_name=ROOM_PARAM_NAME, address_param_name=ADDRESS_PARAM_NAME,
        device_uid_param_name=DEVICE_UID_PARAM_NAME, annotation_symbol=ANNOTATION_SYMBOL,
        label_offset_mm=NODE_LABEL_OFFSET_MM, max_row_width_mm=MAX_ROW_WIDTH_MM
    )

    cable_line_ids = []
    if CABINET_CATEGORY_NAME:
        for group in section_groups:
            cabinet_uid = cabinet_uid_by_group.get(group["key"])
            group_state = new_state["groups"].get(group["key"])
            if cabinet_uid and group_state:
                cable_line_ids.extend(sync_cable_connections(doc, view, group_state, [], cabinet_uid))
    new_state["cable_line_ids"] = cable_line_ids

    state_saved, state_save_error = save_state(view, LAYOUT_PARAM_NAME, new_state)


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

output.print_md(u"### Структурная схема СОТ: {}".format(view_name))

if not state_saved:
    output.print_md(
        u"### ⚠ Раскладка НЕ сохранена в параметр вида «{}»\n\n"
        u"Причина: {}.\n\n"
        u"Без этого параметра повторный запуск не найдёт сегодняшнюю раскладку и "
        u"нарисует все узлы/помещения/этажи заново поверх уже существующих "
        u"(дублирование).".format(LAYOUT_PARAM_NAME, state_save_error)
    )

if BUILDING_PARAM_NAME and BUILDING_FILTER_VALUE:
    output.print_md(u"Корпус (фильтр): **{}**".format(BUILDING_FILTER_VALUE))

level_count = sum(len(group["level_order"]) for group in section_groups)
has_section_blocks = bool(BUILDING_PARAM_NAME or SECTION_PARAM_NAME)

if has_section_blocks:
    output.print_md(u"Блоков «корпус/секция» на схеме: **{}**".format(len(section_groups)))
    for group in section_groups:
        output.print_md(u"- {}: этажей {}, устройств {}".format(
            group["label"], len(group["level_order"]), len(group["items"])
        ))

if CABINET_CATEGORY_NAME:
    groups_without_cabinet = [g for g in section_groups if g["key"] not in cabinet_uid_by_group]
    if groups_without_cabinet:
        if has_section_blocks:
            output.print_md(
                u"⚠ Категория «Шкаф» задана («{}»), но в этих блоках шкафа нет — "
                u"линии и стояк там не нарисованы: {}".format(
                    CABINET_CATEGORY_NAME, u", ".join(g["label"] for g in groups_without_cabinet)
                )
            )
        else:
            output.print_md(
                u"⚠ Категория «Шкаф» задана («{}»), но среди устройств на схеме такого нет — "
                u"линии не нарисованы.".format(CABINET_CATEGORY_NAME)
            )
    output.print_md(u"Линий к шкафам нарисовано: **{}**".format(len(new_state.get("cable_line_ids", []))))
    for group in section_groups:
        extra = cabinet_extra_by_group.get(group["key"])
        if extra:
            output.print_md(
                u"{}найдено ещё {} устройств категории «Шкаф» кроме первого — "
                u"линии рисуются только к одному (по порядку адреса).".format(
                    (group["label"] + u": ") if group["label"] else u"", extra
                )
            )
output.print_md(u"{}, этажей: {}, устройств на схеме: {}".format(
    u"Вид создан заново" if is_new_view else u"Вид обновлён",
    level_count, len(all_report_rows)
))
output.print_md(
    u"Помещения: не тронуто {}, сдвинуто {}, создано {}, перерисовано {}, удалено {}".format(
        sync_stats.get("rooms_unchanged", 0), sync_stats.get("rooms_moved", 0),
        sync_stats.get("rooms_created", 0), sync_stats.get("rooms_redrawn", 0),
        sync_stats.get("rooms_removed", 0)
    )
)
if sync_stats.get("tags_added", 0):
    output.print_md(
        u"Добавлено марок задним числом на уже стоявшие узлы (раньше не было — "
        u"например, марка не была выбрана в настройках при первом запуске): "
        u"**{}**.".format(sync_stats["tags_added"])
    )
output.print_md(
    u"Этажи: не тронуто {}, сдвинуто {}, создано {}, перерисовано {}, удалено {}".format(
        sync_stats.get("levels_unchanged", 0), sync_stats.get("levels_moved", 0),
        sync_stats.get("levels_created", 0), sync_stats.get("levels_redrawn", 0),
        sync_stats.get("levels_removed", 0)
    )
)
output.print_md(
    u"Помещение (реального устройства): уже было заполнено — {}, найдено в связи — {}, не найдено — {}".format(
        room_counters["already_set"], room_counters["looked_up"], room_counters["not_found"]
    )
)

if room_counters["not_found"]:
    output.print_md(
        u"Для устройств без найденного помещения (**{}** шт.) на схеме будет "
        u"группа «(пусто)» — либо точка устройства не попадает ни в один Room "
        u"связанной модели, либо не подключена сама связь.".format(room_counters["not_found"])
    )

if unmatched_report:
    output.print_md(u"### Не размещено (нет категории/схемного семейства) — {}".format(len(unmatched_report)))
    for level_label, room_key, device in unmatched_report:
        try:
            device_name = device.Name
        except:
            device_name = u"?"
        output.print_md(u"- {} / {} — {} (ID {})".format(level_label, room_key, device_name, device.Id.IntegerValue))

forms.alert(
    u"{}"
    u"Готово.\n\n"
    u"Вид: {} ({})\n"
    u"Этажей: {}\n"
    u"Устройств на схеме: {}\n"
    u"Не размещено (нет категории/схемного семейства): {}\n\n"
    u"Подробности (включая статистику "
    u"не тронуто/сдвинуто/создано/перерисовано/удалено) — в окне вывода pyRevit.".format(
        (u"ВНИМАНИЕ: раскладка НЕ сохранена в параметр вида «{}».\nПричина: {}.\n"
         u"Без этого параметра следующий запуск продублирует схему.\n\n".format(
             LAYOUT_PARAM_NAME, state_save_error
         )
         if not state_saved else u""),
        view_name, (u"новый" if is_new_view else u"обновлён"),
        level_count, len(all_report_rows), len(unmatched_report)
    )
)

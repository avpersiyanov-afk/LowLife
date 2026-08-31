# -*- coding: utf-8 -*-
__title__ = "Структурная\nсхема СПС"
__doc__ = (
    "Строит/обновляет структурную схему СПС (пожарная сигнализация и "
    "электрооборудование — панели/изоляторы). Сама находит на модели все "
    "устройства, тип которых сопоставлен категории в настройках СПС, "
    "группирует их по этажу (подпись — «Этаж N (отметка)», порядок по "
    "отметке: отрицательные — внизу схемы, глубже — ниже; положительные — "
    "выше, чем больше отметка) и по помещению.\n\n"
    "Повторный запуск не пересоздаёт схему с нуля: обновляется вид с именем "
    "из настроек СПС (создаётся с этим именем, если его ещё нет), раскладка "
    "предыдущего запуска хранится в служебном параметре этого вида — "
    "обновляются только этаж/помещение/устройство, где реально что-то "
    "изменилось (добавилось/пропало/переехало), остальное остаётся как было, "
    "теми же элементами. Соседи справа/ниже места изменения сдвигаются, "
    "чтобы закрыть/освободить место. Шаблон вида (если выбран в настройках) "
    "применяется на каждом запуске.\n\n"
    "Если в настройках заданы параметр корпуса/секции и значение для "
    "фильтрации — берутся только устройства с этим значением (остальные "
    "игнорируются). Чтобы вести отдельную схему по каждому корпусу, "
    "задайте для каждого своё имя вида и своё значение фильтра в настройках.\n\n"
    "Ответвления изоляторов (устройства, подключённые к изолятору — состав "
    "берётся из фактической электрической цепи «изолятор -> устройства», "
    "кнопка «Цепи изолятор-устройства СПС», а не из адреса или геометрии) "
    "рисуются НЕ в своём обычном помещении, а отдельным рядом-веткой прямо "
    "под изолятором на схеме (тот же шаг между узлами и та же рамка, что у "
    "обычного помещения, зазор 5 мм), — итог похож на дерево, растущее из "
    "кольца. Если ВСЕ устройства ветви — в том же помещении, что и сам "
    "изолятор, отдельная рамка не рисуется — ветка встаёт прямо под "
    "изолятором внутри рамки его же помещения («Смещение ветки в том же "
    "помещении, мм» в настройках СПС); место под неё (и по высоте, и по "
    "ширине) резервируется заранее, вместе с общей раскладкой этажа. "
    "Устройства ветви часто физически разбросаны по нескольким разным "
    "помещениям — если в настройках задан параметр «Имя лота на помещении "
    "в связанной модели», для таких устройств сначала смотрится этот "
    "параметр у помещения связи, в которое попадает точка устройства, и, "
    "если он заполнен, его значение принудительно записывается в параметр "
    "помещения устройства (и на реальный элемент в модели, и на схемный "
    "узел) вместо обычного имени/номера — так несколько физически разных "
    "помещений, отмеченных одним «лотом», на схеме читаются одной общей "
    "рамкой. У изолятора без такой цепи ответвления нет — его устройства "
    "остаются в общей раскладке по помещению как обычно.\n\n"
    "Если в настройках задана категория «Шкаф»/«Панель» — рисуются линии до "
    "него шинной топологией: на каждом этаже один общий горизонтальный "
    "коллектор чуть ниже узлов, от каждого узла к нему короткий вертикальный "
    "отвод, коллекторы всех этажей выходят на один общий вертикальный "
    "стояк слева от рамок этажей.\n\n"
    "Кроме этого, для каждого шлейфа (адрес устройства «панель.шлейф.номер») "
    "рисуется кольцевой шлейф: внутри каждого помещения, где есть устройства "
    "этого шлейфа (включая панель, если она там же), — один отрезок на "
    "высоте самих узлов, проходящий через них (без отхода вниз). Переход в "
    "ЛЮБОЕ другое помещение — хоть соседнее, хоть на другом этаже — только "
    "через один общий стояк слева от рамок этажей, никогда напрямую между "
    "помещениями (иначе линия резала бы чужие рамки, оказавшиеся между "
    "ними): от края помещения к стояку идёт короткий спуск в свободный "
    "зазор под рамкой, а не по прямой через чужие помещения. Кольцевой "
    "интерфейс идёт «туда» и «обратно» по одному и тому же маршруту, "
    "поэтому вся структура (отрезки внутри помещений + спуски + стояк) "
    "рисуется в два прохода со сдвигом 3 мм между ними. Шлейф без панели "
    "среди узлов схемы (панель не сопоставлена ни одной категории в "
    "настройках) рисуется без замыкания на неё.\n\n"
    "Оба вида линий (к шкафу и кольца/ответвления) не редактируются "
    "вручную — на каждом запуске перерисовываются заново по актуальным "
    "позициям, и оба выключаются ОДНИМ полем настроек. На больших моделях "
    "их построение заметно дольше, чем сама раскладка узлов по этажам/"
    "помещениям (включая ряды-ветки ответвлений — те строятся всегда, "
    "линий не касается). Чтобы сначала проверить/поправить раскладку без "
    "ожидания линий, впишите «нет» в настройках СПС в поле «Рисовать "
    "кольцевые шлейфы и ответвления» — раскладка построится как обычно, "
    "линии просто не рисуются (старые, если были, удаляются). Верните «да» "
    "(или очистите поле), когда раскладка устроит, и запустите ещё раз — "
    "линии достроятся.\n\n"
    "Марки узлов (IndependentTag) — тоже отдельный переключатель, «Ставить "
    "марки узлов»: сама вставка марки — штатный вызов Revit API, который на "
    "некоторых моделях занимает секунду и больше НА КАЖДУЮ марку, и легко "
    "становится основным временем построения схемы при сотнях устройств "
    "(на практике наблюдалось на порядок дольше, чем всё остальное вместе "
    "взятое). Впишите «нет», чтобы сначала построить/поправить раскладку "
    "без марок, добавить их отдельным запуском, когда раскладка устроит."
)
__author__ = "Pipers"

import time

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    ElementId, FilteredElementCollector, BuiltInCategory, ViewFamilyType, ViewFamily, ViewDrafting
)
from pyrevit import revit, forms, script as pyrevit_script

try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict

from lowlife.params import get_string_param, set_param_any
from lowlife.skud import category_by_type_id
from lowlife import fire_alarm_settings
from lowlife.fire_alarm_settings import (
    get_settings_silent, get_schematic_category_symbols, get_schematic_category_device_type_ids,
    get_node_annotation_symbol, get_view_template, SCHEMATIC_SOURCE_CATEGORIES
)
from lowlife.sot_levels import group_elements_by_level, sorted_level_names, get_level_label
from lowlife.sot_schematic import sync_levels, sync_cable_connections, delete_elements, STEP_MM
from lowlife.sot_layout_state import find_layout_view, save_state
from lowlife.room_info import (
    get_point as get_room_point, find_room_info, find_room_param_value, format_room_value
)
from lowlife.fire_alarm import parse_device_address, parse_panel_address, group_devices_by_loop, is_isolator
from lowlife.fire_alarm_circuits import isolator_branch_device_map
from lowlife.fire_alarm_schematic import (
    sync_loop_connections, sync_isolator_satellites, node_placement_from_state, satellite_extra_bottom_mm
)

fire_alarm_settings.set_system("SPS")

doc = revit.doc
output = pyrevit_script.get_output()

# --- замеры времени по этапам (чтобы понять, где реально уходит время на
# больших моделях, вместо гаданий) ---

_timings = []
_last_mark_time = [time.time()]


def _mark(label):
    now = time.time()
    _timings.append((label, now - _last_mark_time[0]))
    _last_mark_time[0] = now


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

fire_alarm_settings.require(settings, [
    "room_param_name", "room_number_param_name", "device_address_param",
    "node_label_offset_mm", "schematic_view_name", "layout_param_name", "device_uid_param_name",
    "schematic_device_categories_text",
])

LEVEL_PARAM_NAME = settings["level_param_name"]
ROOM_PARAM_NAME = settings["room_param_name"]
ROOM_NUMBER_PARAM_NAME = settings["room_number_param_name"]
ADDRESS_PARAM_NAME = settings["device_address_param"]
BUILDING_PARAM_NAME = settings["building_param_name"]
BUILDING_FILTER_VALUE = settings["building_filter_value"].strip()
SCHEMATIC_VIEW_NAME = settings["schematic_view_name"]
LAYOUT_PARAM_NAME = settings["layout_param_name"]
DEVICE_UID_PARAM_NAME = settings["device_uid_param_name"]
CABINET_CATEGORY_NAME = settings["cabinet_category_name"].strip()
DRAW_LOOP_LINES = settings.get("draw_loop_lines", u"да").strip().lower() not in (u"нет", u"no", u"0", u"false")
DRAW_TAGS = settings.get("draw_tags", u"да").strip().lower() not in (u"нет", u"no", u"0", u"false")

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

try:
    SAME_ROOM_BRANCH_OFFSET_MM = float(
        (settings.get("same_room_branch_offset_mm") or u"").replace(u",", u".") or 0.0
    )
except (ValueError, AttributeError):
    SAME_ROOM_BRANCH_OFFSET_MM = 0.0
if SAME_ROOM_BRANCH_OFFSET_MM < 0.0:
    SAME_ROOM_BRANCH_OFFSET_MM = 0.0

BRANCH_LOT_ROOM_PARAM_NAME = settings.get("branch_lot_room_param_name") or u""

# Марки (IndependentTag) — штатный вызов Revit API, который на некоторых
# моделях стоит секунду и больше НА КАЖДУЮ марку (см. докстринг кнопки) —
# при DRAW_TAGS=False сразу берём None: place_node_annotation ловит это в
# своём try/except (обращение к .IsActive у None) и просто не пытается
# создать марку — без единого лишнего вызова IndependentTag.Create.
ANNOTATION_SYMBOL = get_node_annotation_symbol(doc, settings) if DRAW_TAGS else None
VIEW_TEMPLATE = get_view_template(doc, settings)

if ANNOTATION_SYMBOL is None and DRAW_TAGS:
    forms.alert(
        u"Не выбрана марка узла в настройках СПС — марки над схемными "
        u"семействами ставиться не будут.\n\n"
        u"Откройте «Параметры СПС» и выберите марку узла, чтобы включить их."
    )

CATEGORY_SYMBOLS = get_schematic_category_symbols(doc, settings)

if not CATEGORY_SYMBOLS:
    forms.alert(
        u"Не выбран ни один тип схемного семейства для категорий устройств "
        u"структурной схемы СПС.\n\n"
        u"Откройте «Параметры СПС», обновите список категорий и выберите "
        u"схемное семейство для каждой из них.",
        exitscript=True
    )

CATEGORY_DEVICE_TYPE_IDS = get_schematic_category_device_type_ids(settings)

if not CATEGORY_DEVICE_TYPE_IDS:
    forms.alert(
        u"Не выбраны реальные типы устройств ни для одной категории "
        u"структурной схемы СПС.\n\n"
        u"Откройте «Параметры СПС» и выберите типы устройств модели для "
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

for cat_key in SCHEMATIC_SOURCE_CATEGORIES:
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
        u"в настройках СПС.",
        exitscript=True
    )

_mark(u"Автосбор устройств")


# ------------------------------------------------------------
# ФИЛЬТР ПО КОРПУСУ/СЕКЦИИ (оба поля заданы в настройках — без диалога)
# ------------------------------------------------------------

if BUILDING_PARAM_NAME and BUILDING_FILTER_VALUE:
    def _element_building(el):
        value = get_string_param(el, BUILDING_PARAM_NAME)
        return value.strip() if value and value.strip() else u"(без корпуса)"

    elements = [el for el in elements if _element_building(el) == BUILDING_FILTER_VALUE]

    if not elements:
        forms.alert(
            u"После фильтрации по корпусу/секции «{}» не осталось устройств.\n\n"
            u"Проверьте значение в «Параметры СПС» — «Значение корпуса/секции для "
            u"фильтрации».".format(BUILDING_FILTER_VALUE),
            exitscript=True
        )


_mark(u"Фильтр по корпусу/секции")


# ------------------------------------------------------------
# ШКАФ — линии от остальных узлов к нему (см. sync_cable_connections)
# ------------------------------------------------------------

CABINET_UID = None
cabinet_extra_count = 0

if CABINET_CATEGORY_NAME:
    cabinet_elements = [el for el in elements if category_for_device(el) == CABINET_CATEGORY_NAME]

    if cabinet_elements:
        cabinet_elements.sort(key=lambda el: get_string_param(el, ADDRESS_PARAM_NAME) or u"")
        CABINET_UID = cabinet_elements[0].UniqueId
        cabinet_extra_count = len(cabinet_elements) - 1


# ------------------------------------------------------------
# ИЗОЛЯТОРЫ И ИХ ОТВЕТВЛЕНИЯ (для раскладки-спутника — и, если включено,
# для линий кольца)
# ------------------------------------------------------------
#
# Устройства ответвления убираются из обычной раскладки по помещению
# (иначе оказались бы на схеме дважды) и рисуются отдельным рядом под
# своим изолятором (sync_isolator_satellites) — см. её докстринг в
# fire_alarm_schematic.py. Состав ответвления — из фактической
# электрической цепи "изолятор -> устройства" (build_isolator_device_circuits),
# а не по адресу/геометрии — см. докстринг lowlife.fire_alarm_loops о том,
# почему по одному адресу магистраль от ветви не отличить.

element_ids_set = set(el.Id.IntegerValue for el in elements)

isolator_keyword = settings.get("isolator_keyword") or u"изолятор"
isolator_ids = set(el.Id.IntegerValue for el in elements if is_isolator(el, isolator_keyword))

_mark(u"Поиск изоляторов (is_isolator по всем устройствам)")

branch_devices_by_isolator_id = isolator_branch_device_map(doc, isolator_ids) if isolator_ids else {}

_mark(u"Поиск ответвлений изоляторов (обход электрических цепей)")

# {изолятор (элемент): [устройства ветви (элементы), ...]} — только
# изоляторы, реально попавшие в elements (иначе рисовать спутник не для
# чего — самого изолятора на схеме не будет), и только устройства ветви,
# тоже попавшие в elements (иначе размещать нечего).
satellite_branches_by_isolator = OrderedDict()
branch_device_ids = set()

for el in elements:
    if el.Id.IntegerValue not in isolator_ids:
        continue
    branch_members = [
        d for d in (branch_devices_by_isolator_id.get(el.Id.IntegerValue) or [])
        if d.Id.IntegerValue in element_ids_set
    ]
    if not branch_members:
        continue
    branch_members.sort(key=lambda d: parse_device_address(get_string_param(d, ADDRESS_PARAM_NAME)) or (0, 0, 0))
    satellite_branches_by_isolator[el] = branch_members
    branch_device_ids.update(d.Id.IntegerValue for d in branch_members)

branch_count = len(satellite_branches_by_isolator)
branch_device_count = len(branch_device_ids)

_mark(u"Сборка веток ответвлений (спутников)")


# ------------------------------------------------------------
# ГРУППИРОВКА ПО ЭТАЖУ
# ------------------------------------------------------------

level_groups = group_elements_by_level(doc, elements, LEVEL_PARAM_NAME)
level_order = sorted_level_names(level_groups)
level_labels = dict((name, get_level_label(name)) for name in level_order)

_mark(u"Группировка по этажу (уровень элемента)")


def resolve_room_value(doc, el, counters, is_branch=False):
    """
    Значение параметра ROOM_PARAM_NAME на устройстве, если оно уже
    заполнено; если пусто — ищет помещение в связанной модели сам и
    записывает найденное значение на устройство, чтобы при повторном
    запуске схемы и других кнопках оно уже было под рукой.

    is_branch — устройство ушло в ветку изолятора (branch_device_ids, см.
    вызывающий код). Только для таких устройств, и только если в
    настройках задан BRANCH_LOT_ROOM_PARAM_NAME («Имя лота» на самом
    ПОМЕЩЕНИИ в связанной модели, не на устройстве): сначала смотрим этот
    параметр у Room, в который попадает точка устройства — если он
    заполнен, ПРИНУДИТЕЛЬНО (даже если ROOM_PARAM_NAME на устройстве уже
    чем-то заполнен) записываем его значение в ROOM_PARAM_NAME и
    возвращаем, минуя обычный поиск имени/номера помещения. Устройства
    ветви физически часто разбросаны по нескольким помещениям — обычный
    геометрический поиск по каждой точке отдельно совершенно корректно
    находит им разные помещения, а "Имя лота" — способ вручную указать в
    связанной модели, что несколько таких помещений на самом деле одна
    логическая зона ветки. Если параметр не задан в настройках, или у
    найденного Room пуст — просто продолжаем обычной логикой ниже (эта
    ветка не отличается от любого другого устройства).
    """
    if is_branch and BRANCH_LOT_ROOM_PARAM_NAME:
        point = get_room_point(el)
        lot_value = find_room_param_value(doc, point, BRANCH_LOT_ROOM_PARAM_NAME)
        if lot_value:
            set_param_any(el, ROOM_PARAM_NAME, lot_value)
            counters["lot_written"] += 1
            return lot_value

    room_value = get_string_param(el, ROOM_PARAM_NAME)

    if room_value and room_value.strip():
        counters["already_set"] += 1
        return room_value.strip()

    point = get_room_point(el)
    room_name, room_number = find_room_info(doc, point, ROOM_NUMBER_PARAM_NAME)
    looked_up_value = format_room_value(room_name, room_number)

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
        u"структурную схему СПС туда поставить нельзя.\n\n"
        u"Переименуйте существующий вид либо измените имя вида в «Параметры "
        u"СПС».".format(SCHEMATIC_VIEW_NAME),
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
room_counters = {"already_set": 0, "looked_up": 0, "not_found": 0, "lot_written": 0}
sync_stats = {}

with revit.Transaction(u"Sync SPS Schematic"):
    # Сначала помещения — сразу для ВСЕЙ выборки, одним проходом, а не по
    # одному внутри группировки по этажам. ВКЛЮЧАЯ устройства ветвей
    # изоляторов — им это помещение не нужно для обычной раскладки (они
    # не попадут в level_room_groups, см. ниже), но нужно как значение
    # параметра: sync_isolator_satellites сравнивает его с помещением
    # изолятора (same_room) и пишет как подпись/параметр на схемный узел
    # ветки, а EXTRA_ROOM_WIDTH_MM ниже — как условие резерва ширины;
    # если пропустить resolve_room_value для них, у устройства, чьё
    # помещение никогда не заполняли вручную, оно так и останется
    # пустым навсегда (заполнить его больше некому). is_branch — только
    # для них смотрится "Имя лота" на помещении в связи (см. докстринг
    # resolve_room_value). Расстановка (level_room_groups/sync_levels)
    # идёт уже по готовым значениям.
    room_value_by_id = {}

    for el in elements:
        el_id = el.Id.IntegerValue
        room_value_by_id[el_id] = resolve_room_value(
            doc, el, room_counters, is_branch=(el_id in branch_device_ids)
        )

    _mark(u"Определение помещений (resolve_room_value, поиск в связи)")

    # --- доп. ширина под ветки изоляторов "в том же помещении" (см.
    # fire_alarm_schematic.sync_isolator_satellites) — считается ЗАРАНЕЕ,
    # до sync_levels, чтобы попасть в саму раскладку (перенос по
    # max_row_width_mm, позиции соседних помещений в ряду), а не
    # приклеиваться поверх уже готового макета этажа постфактум, когда
    # двигать/учитывать в лимите уже поздно. "В том же помещении" — все
    # устройства ветви (после resolve_room_value выше, включая возможную
    # подстановку по "Имени лота") резолвились в ТО ЖЕ помещение, что и
    # сам изолятор; если хотя бы одно отличается — ветка не "в том же
    # помещении", ширина под неё не резервируется здесь (см.
    # sync_isolator_satellites — там она уйдёт в отдельную рамку-
    # спутник). Консервативно (по числу устройств ветви * STEP_MM, без
    # точного знания X изолятора внутри помещения) — лучше немного
    # лишнего места, чем наложение на соседа; если изоляторов "в том же
    # помещении" в одном помещении несколько — ширина суммируется по всем.
    level_name_by_id = {}
    for level_name in level_order:
        for el in level_groups[level_name]["elements"]:
            level_name_by_id[el.Id.IntegerValue] = level_name

    extra_room_width_mm = {}
    for isolator_el, branch_devices in satellite_branches_by_isolator.items():
        isolator_id = isolator_el.Id.IntegerValue
        isolator_room_value = room_value_by_id.get(isolator_id)
        if not isolator_room_value:
            continue

        valid_branch_devices = [
            d for d in branch_devices
            if category_for_device(d) and CATEGORY_SYMBOLS.get(category_for_device(d)) is not None
        ]
        if not valid_branch_devices:
            continue

        same_room = all(
            room_value_by_id.get(d.Id.IntegerValue) == isolator_room_value
            for d in valid_branch_devices
        )
        if not same_room:
            continue

        level_name = level_name_by_id.get(isolator_id)
        if level_name is None:
            continue

        extra_mm = len(valid_branch_devices) * STEP_MM
        level_extra = extra_room_width_mm.setdefault(level_name, {})
        level_extra[isolator_room_value] = level_extra.get(isolator_room_value, 0.0) + extra_mm

    _mark(u"Резерв ширины под ветки изоляторов в том же помещении")

    level_room_groups = OrderedDict()

    for level_name in level_order:
        room_groups = OrderedDict()

        for el in level_groups[level_name]["elements"]:
            if el.Id.IntegerValue in branch_device_ids:
                # Идёт в ряд-спутник своего изолятора (sync_isolator_satellites
                # ниже), не в обычную раскладку по помещению — несмотря на
                # то, что room_value_by_id для него тоже посчитан (см. выше).
                continue

            room_value = room_value_by_id[el.Id.IntegerValue]
            room_key = room_value if room_value else u"(пусто)"

            if room_key not in room_groups:
                room_groups[room_key] = []
            room_groups[room_key].append(el)

        level_room_groups[level_name] = room_groups

    _mark(u"Раскладка по этажам (level_room_groups)")

    if is_new_view:
        view = ViewDrafting.Create(doc, drafting_type_id)
        view.Name = SCHEMATIC_VIEW_NAME
        view.Scale = 1

    view_name = view.Name

    try:
        view.ViewTemplateId = VIEW_TEMPLATE.Id if VIEW_TEMPLATE is not None else ElementId.InvalidElementId
    except:
        pass

    # timing_levels/timing_satellites — детальная разбивка (сек.) по видам
    # Revit-операций внутри _place_room_group (текст/линии/активация типа/
    # вставка экземпляра/параметры/марка), см. её докстринг — печатается в
    # отчёте ниже, чтобы видеть, что именно на этой модели ест время.
    timing_levels = {}
    timing_satellites = {}

    # mirror_rows=False — у СКС зеркалирование нечётных строк нужно,
    # чтобы линия "устройство -> шкаф" не пересекала подпись соседней
    # строки; у СПС кольцевой шлейф идёт напрямую через устройства
    # строки на её собственной высоте (см. fire_alarm_schematic.py), а
    # не отдельным отводом выше/ниже — зеркалировать нечего, все строки
    # выглядят одинаково (подпись/марка сверху).
    satellite_extra_bottom = satellite_extra_bottom_mm(SAME_ROOM_BRANCH_OFFSET_MM)

    new_state, all_report_rows = sync_levels(
        doc, view, level_order, level_room_groups, level_labels, CATEGORY_SYMBOLS, category_for_device,
        ROOM_PARAM_NAME, ADDRESS_PARAM_NAME, DEVICE_UID_PARAM_NAME, ANNOTATION_SYMBOL,
        NODE_LABEL_OFFSET_MM, previous_state, unmatched_report, sync_stats,
        extra_bottom_mm=satellite_extra_bottom, timing=timing_levels,
        max_row_width_mm=MAX_ROW_WIDTH_MM, mirror_rows=False,
        extra_room_width_mm=extra_room_width_mm
    )

    _mark(u"sync_levels (раскладка этажей/помещений/устройств)")

    # --- ряды-спутники ответвлений изоляторов (раскладка, без линий) ---
    # Всегда (не зависит от DRAW_LOOP_LINES — это про расположение
    # устройств, а не про провода).

    old_satellite_ids = previous_state.get("satellite_ids", [])
    if satellite_branches_by_isolator:
        isolator_branches_by_uid = OrderedDict(
            (isolator_el.UniqueId, devices) for isolator_el, devices in satellite_branches_by_isolator.items()
        )
        new_state["satellite_ids"] = sync_isolator_satellites(
            doc, view, old_satellite_ids, isolator_branches_by_uid, new_state,
            CATEGORY_SYMBOLS, category_for_device, ROOM_PARAM_NAME, ADDRESS_PARAM_NAME,
            DEVICE_UID_PARAM_NAME, ANNOTATION_SYMBOL, NODE_LABEL_OFFSET_MM,
            timing=timing_satellites, same_room_branch_offset_mm=SAME_ROOM_BRANCH_OFFSET_MM
        )
    else:
        delete_elements(doc, old_satellite_ids)
        new_state["satellite_ids"] = []

    _mark(u"Ряды-спутники ответвлений")

    # --- провода: пока выключены целиком (и «шкафные», и кольца/ответвления) ---
    # DRAW_LOOP_LINES управляет ОБОИМИ видами линий, пока раскладка
    # (в т.ч. новые ряды-спутники выше) не устроит — см. настройки СПС.
    # sync_cable_connections/sync_loop_connections вызываются в любом
    # случае (с cabinet_uid=None / пустым списком колец при выключенном
    # флаге), чтобы старые линии от предыдущего запуска с включёнными
    # проводами гарантированно удалились, а не остались висеть.

    if CABINET_CATEGORY_NAME:
        old_cable_line_ids = previous_state.get("cable_line_ids", [])
        new_state["cable_line_ids"] = sync_cable_connections(
            doc, view, new_state, old_cable_line_ids, CABINET_UID if DRAW_LOOP_LINES else None
        )

    _mark(u"Линии к шкафу")

    # --- кольцевые шлейфы: панель -> устройство №1 -> ... -> №N -> обратно ---

    loops_for_drawing = []
    loops_without_panel = 0

    if DRAW_LOOP_LINES:
        address_by_id = {}
        panel_by_number = {}

        for el in elements:
            raw = get_string_param(el, ADDRESS_PARAM_NAME)
            parsed = parse_device_address(raw)
            if parsed is not None:
                address_by_id[el.Id.IntegerValue] = parsed
            else:
                panel_num = parse_panel_address(raw)
                if panel_num is not None:
                    panel_by_number[panel_num] = el

        loops_by_key = group_devices_by_loop(elements, address_by_id)

        # Ответвления (изолятор -> его branch_devices) — те же самые,
        # что уже посчитаны выше для раскладки-спутника; здесь только
        # достаём UniqueId для sync_loop_connections.
        branches_by_isolator_uid = dict(
            (isolator_el.UniqueId, [d.UniqueId for d in devices])
            for isolator_el, devices in satellite_branches_by_isolator.items()
        )

        for (panel_num, _loop_num), devices_in_loop in loops_by_key.items():
            panel_el = panel_by_number.get(panel_num)
            panel_uid = panel_el.UniqueId if panel_el is not None else None
            if panel_uid is None:
                loops_without_panel += 1

            branches = {}
            for device in devices_in_loop:
                if device.Id.IntegerValue not in isolator_ids:
                    continue
                branch_uids = branches_by_isolator_uid.get(device.UniqueId)
                if branch_uids:
                    branches[device.UniqueId] = branch_uids

            # group_devices_by_loop работает по elements (полный список,
            # ответвления оттуда не убирались) — исключаем их здесь: у
            # них нет отдельного узла на основной раскладке (только в
            # спутнике под изолятором), магистрали идти не к чему.
            loops_for_drawing.append({
                "panel_uid": panel_uid,
                "device_uids": [d.UniqueId for d in devices_in_loop if d.Id.IntegerValue not in branch_device_ids],
                "branches": branches
            })

    # sync_loop_connections вызывается всегда (даже при выключенном
    # DRAW_LOOP_LINES, с пустым loops_for_drawing) — иначе линии, оставшиеся
    # от предыдущего запуска с включённым флагом, не удалились бы.
    node_placement = node_placement_from_state(new_state) if DRAW_LOOP_LINES else {}
    old_loop_line_ids = previous_state.get("loop_line_ids", [])
    new_state["loop_line_ids"] = sync_loop_connections(doc, view, old_loop_line_ids, loops_for_drawing, node_placement)

    _mark(u"Линии колец/ответвлений")

    state_saved, state_save_error = save_state(view, LAYOUT_PARAM_NAME, new_state)

    _mark(u"Сохранение раскладки в параметр вида")


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

output.print_md(u"### Структурная схема СПС: {}".format(view_name))

output.print_md(u"### Время по этапам (сек.)")
_total_time = sum(seconds for _label, seconds in _timings)
for _label, _seconds in _timings:
    output.print_md(u"- {} — **{:.1f}** сек.".format(_label, _seconds))
output.print_md(u"Итого: **{:.1f}** сек.".format(_total_time))

_timing_labels = {
    "text": u"создание+центрирование текста помещения",
    "lines": u"линии рамки (5 отрезков)",
    "symbol_activate": u"активация типа семейства (редко, раз на тип)",
    "instance": u"вставка экземпляра устройства (NewFamilyInstance)",
    "params": u"запись параметров устройства (адрес/помещение/UID)",
    "tag": u"марка узла (IndependentTag)",
}


def _print_timing_breakdown(title, timing_dict):
    if not timing_dict:
        return
    output.print_md(u"### {} — разбивка по операциям (сек.)".format(title))
    for key, seconds in sorted(timing_dict.items(), key=lambda kv: -kv[1]):
        output.print_md(u"- {} — **{:.1f}** сек.".format(_timing_labels.get(key, key), seconds))


_print_timing_breakdown(u"sync_levels", timing_levels)
_print_timing_breakdown(u"Ряды-спутники", timing_satellites)

if not state_saved:
    output.print_md(
        u"### ⚠ Раскладка НЕ сохранена в параметр вида «{}»\n\n"
        u"Причина: {}.\n\n"
        u"Без этого параметра повторный запуск не найдёт сегодняшнюю раскладку и "
        u"нарисует все узлы/помещения/этажи заново поверх уже существующих "
        u"(дублирование).".format(LAYOUT_PARAM_NAME, state_save_error)
    )

if BUILDING_PARAM_NAME and BUILDING_FILTER_VALUE:
    output.print_md(u"Корпус/секция (фильтр): **{}**".format(BUILDING_FILTER_VALUE))

if CABINET_CATEGORY_NAME:
    if CABINET_UID is None:
        output.print_md(
            u"⚠ Категория «Шкаф»/«Панель» задана («{}»), но среди устройств на схеме такой нет — "
            u"линии не нарисованы.".format(CABINET_CATEGORY_NAME)
        )
    else:
        cable_count = len(new_state.get("cable_line_ids", []))
        output.print_md(u"Линий к шкафу нарисовано: **{}**".format(cable_count))
        if cabinet_extra_count:
            output.print_md(
                u"Найдено ещё {} устройств категории «Шкаф»/«Панель» кроме первого — "
                u"линии рисуются только к одному (по алфавиту адреса).".format(cabinet_extra_count)
            )

if not DRAW_TAGS:
    output.print_md(
        u"Марки узлов выключены в настройках («Ставить марки узлов» = «нет») — узлы на "
        u"схеме без марок."
    )

if not DRAW_LOOP_LINES:
    output.print_md(
        u"Кольцевые шлейфы и ответвления выключены в настройках («Рисовать кольцевые "
        u"шлейфы...» = «нет») — построена только раскладка узлов."
    )
else:
    output.print_md(
        u"Кольцевых шлейфов найдено: **{}**, линий кольца нарисовано: **{}**".format(
            len(loops_for_drawing), len(new_state.get("loop_line_ids", []))
        )
    )
if loops_without_panel:
    output.print_md(
        u"⚠ У **{}** шлейфов панель не найдена среди узлов схемы (адрес панели не "
        u"разбирается как одно число, либо тип панели не сопоставлен ни одной "
        u"категории в настройках) — кольцо для них не нарисовано.".format(loops_without_panel)
    )
if branch_count:
    output.print_md(
        u"Ответвлений от изоляторов: **{}** ({} устройств) — размещены рядом-веткой "
        u"под своим изолятором (состав из электрической цепи «изолятор -> "
        u"устройства», не из адреса; элементов на схеме под них создано: {}).".format(
            branch_count, branch_device_count, len(new_state.get("satellite_ids", []))
        )
    )

output.print_md(u"{}, этажей: {}, устройств на схеме: {}".format(
    u"Вид создан заново" if is_new_view else u"Вид обновлён",
    len(level_order), len(all_report_rows)
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
    u"Помещение (реального устройства): уже было заполнено — {}, найдено в связи — {}, "
    u"не найдено — {}{}".format(
        room_counters["already_set"], room_counters["looked_up"], room_counters["not_found"],
        u", по «Имени лота» ветви — {}".format(room_counters["lot_written"])
        if room_counters["lot_written"] else u""
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
        len(level_order), len(all_report_rows), len(unmatched_report)
    )
)

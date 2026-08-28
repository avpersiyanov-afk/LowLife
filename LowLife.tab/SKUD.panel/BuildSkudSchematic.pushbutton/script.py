# -*- coding: utf-8 -*-
__title__ = "Структурная\nсхема"
__doc__ = (
    "Строит структурную схему СКУД по цепям контроллеров на отдельном "
    "чертёжном виде (имя — из настроек). Узел-контроллер (типовая группа "
    "деталей) ставится один раз на контроллер; на каждую точку прохода "
    "подбирается группа, чей состав устройств совпадает с составом точки "
    "прохода. Группы разгруппировываются, адреса переносятся, весь JSON-"
    "манифест пишется в служебный параметр вида (для кнопки «Обновить "
    "схему»). Повторный запуск перерисовывает схему заново."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife.geometry import get_element_level
from lowlife.params import get_string_param, set_param_any
from lowlife.scs import safe_element_name
from lowlife.scs_circuits import clean_text_value
from lowlife.skud import collect_controller_devices, parse_category_names
from lowlife.skud_schematic import (
    layout_points_by_level, passage_point_layout_point, device_layout_point,
    passage_points_of, signature_of, classify_members, group_signature,
    match_group_name, signature_text, category_of_from_type_map,
    invert_category_device_type_ids, invert_category_type_id_strings,
)
from lowlife.skud_schematic_manifest import (
    find_schematic_view, save_manifest, empty_manifest,
)
from lowlife import skud_settings
from lowlife.skud_settings import (
    get_settings_silent, get_schematic_category_symbols,
    get_schematic_category_device_type_ids, get_schematic_category_layout_ft,
    load_controller_group_id, load_passage_point_group_ids,
    load_schematic_category_type_ids,
)
from lowlife import room_info_settings

doc = revit.doc
view = None  # определяется ниже: вид с именем SCHEMATIC_VIEW_NAME (или создаётся)

FT_TO_M = 0.3048
M_TO_FT = 1.0 / FT_TO_M
MM_TO_FT = M_TO_FT / 1000.0


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

skud_settings.require(settings, [
    "controller_workset_keyword", "controller_type_keyword", "workset_param_name",
    "circuit_panel_param", "device_address_param",
    "schematic_address_param",
    "schematic_layout_gap_m", "schematic_layout_step_mm",
    "schematic_device_categories_text",
    "schematic_view_name", "manifest_param_name",
])

SCHEMATIC_VIEW_NAME = settings["schematic_view_name"]
MANIFEST_PARAM_NAME = settings["manifest_param_name"]

CONTROLLER_WORKSET_KEYWORD = settings["controller_workset_keyword"]
CONTROLLER_TYPE_KEYWORD = settings["controller_type_keyword"]
WORKSET_PARAM_NAME = settings["workset_param_name"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]

CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
DEVICE_ADDRESS_PARAM = settings["device_address_param"]
PASSAGE_POINT_PARAM = settings.get("passage_point_param") or u""
DEVICE_MARKING_PARAM = settings.get("device_marking_param") or u""

SCHEMATIC_ADDRESS_PARAM = settings["schematic_address_param"]
LAYOUT_GAP_FT = float(settings["schematic_layout_gap_m"]) * M_TO_FT
CATEGORY_STEP_FT = float(settings["schematic_layout_step_mm"]) * MM_TO_FT

DEVICE_CATEGORY_NAMES = parse_category_names(settings["schematic_device_categories_text"])

if not DEVICE_CATEGORY_NAMES:
    forms.alert(
        u"Не заданы категории устройств схемы.\n\n"
        u"Заполните поле «Категории устройств схемы» в настройках СКУД "
        u"(по одному имени категории на строку).",
        exitscript=True
    )

CONTROLLER_CATEGORY_NAME = next(
    (n for n in DEVICE_CATEGORY_NAMES if n.lower() == u"контроллер"), None
)

# Карта {категория: set(id реальных типов)} и обратная — для определения
# категории реального устройства.
CATEGORY_DEVICE_TYPE_IDS = get_schematic_category_device_type_ids(settings)
category_of_real = category_of_from_type_map(
    invert_category_device_type_ids(CATEGORY_DEVICE_TYPE_IDS)
)

# Карта категории для СХЕМНЫХ элементов внутри групп — по типу схемного
# семейства, назначенного категории в настройках.
category_of_schematic = category_of_from_type_map(
    invert_category_type_id_strings(load_schematic_category_type_ids())
)

# Схемные семейства по категории — только для резервной раскладки (no-match).
CATEGORY_SYMBOLS = get_schematic_category_symbols(doc, settings)
CATEGORY_LAYOUT_FT = get_schematic_category_layout_ft(settings)

# Типовые группы.
CONTROLLER_GROUP_ID = load_controller_group_id()
PASSAGE_POINT_GROUP_IDS = load_passage_point_group_ids()

if not CONTROLLER_GROUP_ID or not PASSAGE_POINT_GROUP_IDS:
    forms.alert(
        u"Не выбраны типовые группы структурной схемы.\n\n"
        u"Откройте «Параметры СКУД» → раздел «Типовые группы структурной "
        u"схемы» и выберите узел-контроллер и хотя бы одну группу точки "
        u"прохода.",
        exitscript=True
    )

# Параметр помещения (только для записи в манифест — сюда его пишет
# отдельная кнопка «Помещение точек прохода», здесь только переносим).
ROOM_TARGET_PARAM = room_info_settings.load_saved_values().get("target_param_name") or u""

controller_group_type = doc.GetElement(ElementId(int(CONTROLLER_GROUP_ID)))
if controller_group_type is None:
    forms.alert(
        u"Выбранный узел-контроллер (id {}) не найден в проекте. "
        u"Перевыберите его в «Параметры СКУД».".format(CONTROLLER_GROUP_ID),
        exitscript=True
    )


# ------------------------------------------------------------
# КОНТРОЛЛЕРЫ И ИХ УСТРОЙСТВА
# ------------------------------------------------------------

controller_devices = collect_controller_devices(
    doc, WORKSET_PARAM_NAME, CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD,
    CIRCUIT_PANEL_PARAM, EXCLUDED_DEVICE_KEYWORDS
)

if not controller_devices:
    forms.alert(
        u"Не найдено ни одного контроллера (рабочий набор содержит «{}», "
        u"имя типа содержит «{}»).".format(CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD),
        exitscript=True
    )

controllers_with_devices = []
controllers_without_address = []

for controller, devices in controller_devices:
    controller_addr = clean_text_value(get_string_param(controller, DEVICE_ADDRESS_PARAM))
    if not controller_addr:
        controllers_without_address.append(controller.Name)
        continue
    if not devices:
        continue

    level = get_element_level(doc, controller)
    elevation = level.Elevation if level is not None else 0.0
    controllers_with_devices.append((controller, controller_addr, devices, elevation))

if not controllers_with_devices:
    forms.alert(u"Не найдено ни одного контроллера с адресом и подключёнными устройствами.", exitscript=True)

controllers_with_devices.sort(key=lambda item: (item[3], item[1]))


# ------------------------------------------------------------
# ЧЕРТЁЖНЫЙ ВИД: вид с именем из настроек (для обновления), иначе создаём
# ------------------------------------------------------------

view, previous_manifest, name_conflict = find_schematic_view(
    doc, SCHEMATIC_VIEW_NAME, MANIFEST_PARAM_NAME
)

if name_conflict:
    forms.alert(
        u"В проекте уже есть вид с именем «{}», но это не чертёжный вид.\n\n"
        u"Переименуйте существующий вид либо измените имя вида в «Параметры "
        u"СКУД».".format(SCHEMATIC_VIEW_NAME),
        exitscript=True
    )

is_new_view = view is None

if is_new_view:
    previous_manifest = empty_manifest()

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

base_point = XYZ(0.0, 0.0, 0.0)
level_elevations = [item[3] for item in controllers_with_devices]
insert_points = layout_points_by_level(base_point, level_elevations, LAYOUT_GAP_FT)


# ------------------------------------------------------------
# ХЕЛПЕРЫ РАЗМЕЩЕНИЯ
# ------------------------------------------------------------

def _location_point(el):
    try:
        return el.Location.Point
    except:
        return None


def _sorted_schematic(els):
    """Схемные элементы одной категории — по X, затем Y, для стабильности."""
    def key(el):
        p = _location_point(el)
        return (p.X, p.Y) if p is not None else (0.0, 0.0)
    return sorted(els, key=key)


def _group_by_category_ordered(devices):
    """[(категория, [устройства])] в порядке первого появления категории."""
    order = []
    buckets = {}
    for d in devices:
        cat = category_of_real(d)
        if not cat:
            continue
        if cat not in buckets:
            buckets[cat] = []
            order.append(cat)
        buckets[cat].append(d)
    return [(cat, buckets[cat]) for cat in order]


placed_element_ids = []   # всё нарисованное — для очистки при следующей пересборке


def _track(el_or_id):
    try:
        placed_element_ids.append(el_or_id.Id.IntegerValue)
    except:
        try:
            placed_element_ids.append(int(el_or_id))
        except:
            pass


def _make_line(p_from, p_to):
    try:
        line = Line.CreateBound(p_from, p_to)
        dc = doc.Create.NewDetailCurve(view, line)
        _track(dc)
        return True
    except:
        return False


# ------------------------------------------------------------
# ВСТАВКА
# ------------------------------------------------------------

controllers_placed = 0
passage_points_matched = 0
passage_points_unmatched = 0
devices_addressed = 0
lines_created = 0
cleared_elements = 0
unmatched_report = []
group_read_errors = []

manifest_controllers = []

with revit.Transaction("Build SKUD Schematic"):

    if is_new_view:
        view = ViewDrafting.Create(doc, drafting_type_id)
        view.Name = SCHEMATIC_VIEW_NAME
        view.Scale = 1

    # --- очистка предыдущей схемы (перерисовываем заново) ---
    for old_id in previous_manifest.get("placed_element_ids", []):
        try:
            el = doc.GetElement(ElementId(int(old_id)))
        except:
            el = None
        if el is None:
            continue
        try:
            doc.Delete(el.Id)
            cleared_elements += 1
        except:
            pass

    # --- сигнатуры библиотечных групп точек прохода ---
    pp_group_signatures = {}   # имя -> signature
    pp_group_type_by_name = {}
    for id_str in PASSAGE_POINT_GROUP_IDS:
        try:
            gt = doc.GetElement(ElementId(int(id_str)))
        except:
            gt = None
        if gt is None:
            continue
        gt_name = safe_element_name(gt) or id_str
        sig, _by_cat = group_signature(doc, gt, category_of_schematic)
        if sig is None:
            group_read_errors.append(gt_name)
            continue
        pp_group_signatures[gt_name] = sig
        pp_group_type_by_name[gt_name] = gt

    for (controller, controller_addr, devices, _elevation), insert_pt in zip(
        controllers_with_devices, insert_points
    ):
        # --- узел-контроллер ---
        controller_anchor = insert_pt
        controller_schem_ids = []
        try:
            ctrl_group = doc.Create.PlaceGroup(insert_pt, controller_group_type)
            doc.Regenerate()
            freed = list(ctrl_group.UngroupMembers())
        except:
            freed = []
        if freed:
            controllers_placed += 1
            controller_schem_ids = [mid.IntegerValue for mid in freed]
            for mid in freed:
                _track(mid.IntegerValue)
            by_cat, _sig = classify_members(doc, freed, category_of_schematic)
            for el in by_cat.get(CONTROLLER_CATEGORY_NAME, []):
                if set_param_any(el, SCHEMATIC_ADDRESS_PARAM, controller_addr):
                    devices_addressed += 1
                p = _location_point(el)
                if p is not None:
                    controller_anchor = p

        # --- точки прохода ---
        pps = passage_points_of(devices, PASSAGE_POINT_PARAM, DEVICE_ADDRESS_PARAM)
        manifest_pps = []

        for i, (pp_key, pp_devices) in enumerate(pps.items()):
            sig, uncategorized = signature_of(pp_devices, category_of_real)
            matched_name = match_group_name(sig, pp_group_signatures)
            pp_pt = passage_point_layout_point(insert_pt, i, LAYOUT_GAP_FT)
            manifest_devices = []

            if matched_name:
                passage_points_matched += 1
                gt = pp_group_type_by_name[matched_name]
                try:
                    g = doc.Create.PlaceGroup(pp_pt, gt)
                    doc.Regenerate()
                    freed_pp = list(g.UngroupMembers())
                except:
                    freed_pp = []

                for mid in freed_pp:
                    _track(mid.IntegerValue)
                by_cat_pp, _s = classify_members(doc, freed_pp, category_of_schematic)

                for cat, real_list in _group_by_category_ordered(pp_devices):
                    schem_list = _sorted_schematic(by_cat_pp.get(cat, []))
                    for real_dev, schem_el in zip(real_list, schem_list):
                        addr = clean_text_value(get_string_param(real_dev, DEVICE_ADDRESS_PARAM))
                        if addr and set_param_any(schem_el, SCHEMATIC_ADDRESS_PARAM, addr):
                            devices_addressed += 1
                        if addr and DEVICE_MARKING_PARAM:
                            set_param_any(schem_el, DEVICE_MARKING_PARAM, addr)
                        manifest_devices.append({
                            "real_id": real_dev.Id.IntegerValue,
                            "category": cat,
                            "address": addr or u"",
                            "room": get_string_param(real_dev, ROOM_TARGET_PARAM) or u"" if ROOM_TARGET_PARAM else u"",
                            "schematic_id": schem_el.Id.IntegerValue,
                        })

                if _make_line(controller_anchor, pp_pt):
                    lines_created += 1
            else:
                passage_points_unmatched += 1
                unmatched_report.append(
                    u"Контроллер {} — точка прохода «{}»: нет типовой группы для состава {}. "
                    u"Создайте группу с этим составом.".format(
                        controller_addr, pp_key, signature_text(sig)
                    )
                )
                index_by_category = {}
                for real_dev in pp_devices:
                    cat = category_of_real(real_dev)
                    symbol = CATEGORY_SYMBOLS.get(cat) if cat else None
                    if symbol is None:
                        continue
                    if not symbol.IsActive:
                        symbol.Activate()
                    idx = index_by_category.get(cat, 0)
                    dpt = device_layout_point(pp_pt, CATEGORY_LAYOUT_FT, cat, idx, CATEGORY_STEP_FT)
                    index_by_category[cat] = idx + 1
                    schem_el = doc.Create.NewFamilyInstance(dpt, symbol, view)
                    if schem_el is None:
                        continue
                    _track(schem_el)
                    addr = clean_text_value(get_string_param(real_dev, DEVICE_ADDRESS_PARAM))
                    if addr and set_param_any(schem_el, SCHEMATIC_ADDRESS_PARAM, addr):
                        devices_addressed += 1
                    if addr and DEVICE_MARKING_PARAM:
                        set_param_any(schem_el, DEVICE_MARKING_PARAM, addr)
                    if _make_line(controller_anchor, dpt):
                        lines_created += 1
                    manifest_devices.append({
                        "real_id": real_dev.Id.IntegerValue,
                        "category": cat or u"",
                        "address": addr or u"",
                        "room": get_string_param(real_dev, ROOM_TARGET_PARAM) or u"" if ROOM_TARGET_PARAM else u"",
                        "schematic_id": schem_el.Id.IntegerValue,
                    })

            manifest_pps.append({
                "key": pp_key,
                "signature": [[cat, cnt] for cat, cnt in sig],
                "uncategorized": uncategorized,
                "matched_group": matched_name,
                "unmatched": matched_name is None,
                "devices": manifest_devices,
            })

        manifest_controllers.append({
            "controller_id": controller.Id.IntegerValue,
            "address": controller_addr,
            "insert_point": [insert_pt.X, insert_pt.Y, insert_pt.Z],
            "controller_group": safe_element_name(controller_group_type) or CONTROLLER_GROUP_ID,
            "schematic_element_ids": controller_schem_ids,
            "passage_points": manifest_pps,
        })

    # --- манифест в параметр вида (внутри той же транзакции) ---
    manifest_data = empty_manifest()
    manifest_data["base_point"] = [base_point.X, base_point.Y, base_point.Z]
    manifest_data["placed_element_ids"] = placed_element_ids
    manifest_data["controllers"] = manifest_controllers

    manifest_saved, manifest_save_error = save_manifest(view, MANIFEST_PARAM_NAME, manifest_data)
    view_name = view.Name


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

from pyrevit import script as pyrevit_script
output = pyrevit_script.get_output()

if controllers_without_address:
    output.print_md(u"### Контроллеры без адреса, пропущены ({})".format(len(controllers_without_address)))
    for name in controllers_without_address:
        output.print_md(u"- {}".format(name))

if group_read_errors:
    output.print_md(u"### Не удалось прочитать состав групп ({})".format(len(group_read_errors)))
    output.print_md(u"У этих типов групп нет ни одного размещённого экземпляра — вставьте группу в проект один раз:")
    for name in group_read_errors:
        output.print_md(u"- {}".format(name))

if unmatched_report:
    output.print_md(u"### Точки прохода без типовой группы ({})".format(len(unmatched_report)))
    for line in unmatched_report:
        output.print_md(u"- {}".format(line))

if not manifest_saved:
    output.print_md(
        u"### ⚠ Манифест НЕ сохранён в параметр вида «{}»\n\n"
        u"Причина: {}.\n\n"
        u"Без него повторный запуск не найдёт эту схему и нарисует всё "
        u"заново поверх существующего.".format(MANIFEST_PARAM_NAME, manifest_save_error)
    )

warn = u"" if manifest_saved else u"\n\nВНИМАНИЕ: манифест не сохранён — см. окно вывода."

forms.alert(
    u"Готово. Вид: {}\n\n"
    u"Контроллеров размещено: {}\n"
    u"Точек прохода по группе: {}\n"
    u"Точек прохода без группы (резервная раскладка): {}\n"
    u"Адресов записано: {}\n"
    u"Линий создано: {}\n"
    u"Удалено от прошлой схемы: {}\n"
    u"Контроллеров без адреса (пропущено): {}{}".format(
        view_name,
        controllers_placed,
        passage_points_matched,
        passage_points_unmatched,
        devices_addressed,
        lines_created,
        cleared_elements,
        len(controllers_without_address),
        warn,
    )
)

# -*- coding: utf-8 -*-
__title__ = "Структурная\nсхема"
__doc__ = (
    "Строит и обновляет структурную схему СКУД на отдельном чертёжном виде "
    "(имя — из настроек). Узел-контроллер (типовая группа деталей) ставится "
    "один раз на контроллер; на каждую точку прохода подбирается группа, "
    "чей состав устройств совпадает с составом точки прохода. Повторный "
    "запуск — инкрементальная синхронизация: неизменные точки прохода не "
    "трогаются (ручная раскладка сохраняется), изменившиеся перерисовываются, "
    "пропавшие удаляются. Состояние — JSON в служебном параметре вида."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms, script as pyrevit_script

from lowlife.geometry import get_element_level
from lowlife.params import get_string_param
from lowlife.scs import safe_element_name
from lowlife.scs_circuits import clean_text_value
from lowlife.skud import collect_controller_devices, parse_category_names
from lowlife.skud_schematic import (
    passage_points_of, signature_of, group_signature, match_group_name,
    category_of_from_type_map, invert_category_device_type_ids,
    invert_category_type_id_strings,
)
from lowlife.skud_schematic_sync import sync_schematic
from lowlife.skud_schematic_manifest import (
    find_schematic_view, load_manifest, save_manifest, empty_manifest, raw_manifest,
)
from lowlife import skud_settings
from lowlife.skud_settings import (
    get_settings_silent, get_schematic_category_symbols,
    get_schematic_category_device_type_ids,
    load_controller_group_id, load_passage_point_group_ids,
    load_schematic_category_type_ids,
)
from lowlife import room_info_settings

doc = revit.doc
output = pyrevit_script.get_output()

M_TO_FT = 1.0 / 0.3048
MM_TO_FT = M_TO_FT / 1000.0


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

skud_settings.require(settings, [
    "controller_workset_keyword", "controller_type_keyword", "workset_param_name",
    "circuit_panel_param", "device_address_param",
    "schematic_address_param", "schematic_layout_gap_m", "schematic_layout_step_mm",
    "schematic_device_categories_text",
    "schematic_view_name", "manifest_param_name", "schematic_source_uid_param",
])

CONTROLLER_WORKSET_KEYWORD = settings["controller_workset_keyword"]
CONTROLLER_TYPE_KEYWORD = settings["controller_type_keyword"]
WORKSET_PARAM_NAME = settings["workset_param_name"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]
CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
DEVICE_ADDRESS_PARAM = settings["device_address_param"]
PASSAGE_POINT_PARAM = settings.get("passage_point_param") or u""
DEVICE_MARKING_PARAM = settings.get("device_marking_param") or u""
SCHEMATIC_ADDRESS_PARAM = settings["schematic_address_param"]
SCHEMATIC_SOURCE_UID_PARAM = settings["schematic_source_uid_param"]
SCHEMATIC_VIEW_NAME = settings["schematic_view_name"]
MANIFEST_PARAM_NAME = settings["manifest_param_name"]

LAYOUT_GAP_FT = float(settings["schematic_layout_gap_m"]) * M_TO_FT
FALLBACK_STEP_FT = float(settings["schematic_layout_step_mm"]) * MM_TO_FT   # для no-match

DEVICE_CATEGORY_NAMES = parse_category_names(settings["schematic_device_categories_text"])
if not DEVICE_CATEGORY_NAMES:
    forms.alert(
        u"Не заданы категории устройств схемы (поле «Категории устройств схемы»).",
        exitscript=True
    )
CONTROLLER_CATEGORY_NAME = next(
    (n for n in DEVICE_CATEGORY_NAMES if n.lower() == u"контроллер"), None
)

category_of_real = category_of_from_type_map(
    invert_category_device_type_ids(get_schematic_category_device_type_ids(settings))
)
category_of_schematic = category_of_from_type_map(
    invert_category_type_id_strings(load_schematic_category_type_ids())
)
CATEGORY_SYMBOLS = get_schematic_category_symbols(doc, settings)      # для no-match

CONTROLLER_GROUP_ID = load_controller_group_id()
PASSAGE_POINT_GROUP_IDS = load_passage_point_group_ids()
if not CONTROLLER_GROUP_ID or not PASSAGE_POINT_GROUP_IDS:
    forms.alert(
        u"Не выбраны типовые группы структурной схемы.\n\n"
        u"«Параметры СКУД» → «Типовые группы структурной схемы».",
        exitscript=True
    )

controller_group_type = doc.GetElement(ElementId(int(CONTROLLER_GROUP_ID)))
if controller_group_type is None:
    forms.alert(u"Узел-контроллер (id {}) не найден. Перевыберите в «Параметры СКУД».".format(
        CONTROLLER_GROUP_ID), exitscript=True)

ROOM_TARGET_PARAM = room_info_settings.load_saved_values().get("target_param_name") or u""


# ------------------------------------------------------------
# СИГНАТУРЫ ТИПОВЫХ ГРУПП ТОЧЕК ПРОХОДА
# ------------------------------------------------------------

pp_group_signatures = {}
pp_group_type_by_name = {}
group_read_errors = []

for id_str in PASSAGE_POINT_GROUP_IDS:
    try:
        gt = doc.GetElement(ElementId(int(id_str)))
    except:
        gt = None
    if gt is None:
        continue
    gt_name = safe_element_name(gt) or id_str
    sig, _by = group_signature(doc, gt, category_of_schematic)
    if sig is None:
        group_read_errors.append(gt_name)
        continue
    pp_group_signatures[gt_name] = sig
    pp_group_type_by_name[gt_name] = gt


# ------------------------------------------------------------
# ЖЕЛАЕМОЕ СОСТОЯНИЕ ПО МОДЕЛИ
# ------------------------------------------------------------

def _dev_record(d):
    return {
        "uid": d.UniqueId,
        "id": d.Id.IntegerValue,
        "category": category_of_real(d) or u"",
        "address": clean_text_value(get_string_param(d, DEVICE_ADDRESS_PARAM)) or u"",
        "room": (get_string_param(d, ROOM_TARGET_PARAM) or u"") if ROOM_TARGET_PARAM else u"",
    }


controllers_without_address = []
desired_controllers = []

for controller, devices in collect_controller_devices(
    doc, WORKSET_PARAM_NAME, CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD,
    CIRCUIT_PANEL_PARAM, EXCLUDED_DEVICE_KEYWORDS
):
    addr = clean_text_value(get_string_param(controller, DEVICE_ADDRESS_PARAM))
    if not addr:
        controllers_without_address.append(controller.Name)
        continue
    if not devices:
        continue

    pps = []
    for key, pp_devices in passage_points_of(
        devices, PASSAGE_POINT_PARAM, DEVICE_ADDRESS_PARAM
    ).items():
        sig, uncategorized = signature_of(pp_devices, category_of_real)
        pps.append({
            "key": key,
            "signature": [[c, n] for c, n in sig],
            "uncategorized": uncategorized,
            "matched_group": match_group_name(sig, pp_group_signatures),
            "devices": [_dev_record(d) for d in pp_devices],
        })

    level = get_element_level(doc, controller)
    elevation = level.Elevation if level is not None else 0.0

    desired_controllers.append({
        "uid": controller.UniqueId,
        "id": controller.Id.IntegerValue,
        "address": addr,
        "elevation": elevation,
        "passage_points": pps,
    })

if not desired_controllers:
    forms.alert(u"Не найдено ни одного контроллера с адресом и подключёнными устройствами.",
                exitscript=True)

desired_controllers.sort(key=lambda c: (c["elevation"], c["address"]))


# ------------------------------------------------------------
# ЧЕРТЁЖНЫЙ ВИД + ПРЕДЫДУЩЕЕ СОСТОЯНИЕ
# ------------------------------------------------------------

view, previous_state, name_conflict = find_schematic_view(
    doc, SCHEMATIC_VIEW_NAME, MANIFEST_PARAM_NAME
)

if name_conflict:
    forms.alert(
        u"В проекте есть вид с именем «{}», но это не чертёжный вид. "
        u"Переименуйте его или измените имя в «Параметры СКУД».".format(SCHEMATIC_VIEW_NAME),
        exitscript=True
    )

is_new_view = view is None
drafting_type_id = None
legacy_ids = []

if is_new_view:
    previous_state = empty_manifest()
    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements():
        try:
            if vft.ViewFamily == ViewFamily.Drafting:
                drafting_type_id = vft.Id
                break
        except:
            continue
    if drafting_type_id is None:
        forms.alert(u"В проекте не найден ViewFamilyType для чертёжных видов (Drafting).",
                    exitscript=True)
else:
    raw = raw_manifest(view, MANIFEST_PARAM_NAME)
    if isinstance(raw, dict) and raw.get("schema_version") != 2:
        legacy_ids = list(raw.get("placed_element_ids", []))       # миграция v1 -> v2
    previous_state = load_manifest(view, MANIFEST_PARAM_NAME)


# ------------------------------------------------------------
# СИНХРОНИЗАЦИЯ
# ------------------------------------------------------------

cfg = {
    "category_of_schematic": category_of_schematic,
    "schematic_address_param": SCHEMATIC_ADDRESS_PARAM,
    "device_marking_param": DEVICE_MARKING_PARAM,
    "source_uid_param": SCHEMATIC_SOURCE_UID_PARAM,
    "controller_group_type": controller_group_type,
    "pp_group_types_by_name": pp_group_type_by_name,
    "controller_category_name": CONTROLLER_CATEGORY_NAME,
    "category_symbols": CATEGORY_SYMBOLS,
    "fallback_step_ft": FALLBACK_STEP_FT,
    "layout_gap_ft": LAYOUT_GAP_FT,
}

with revit.Transaction("Sync SKUD Schematic"):
    if is_new_view:
        view = ViewDrafting.Create(doc, drafting_type_id)
        view.Name = SCHEMATIC_VIEW_NAME
        view.Scale = 1

    if legacy_ids:
        for old_id in legacy_ids:
            try:
                el = doc.GetElement(ElementId(int(old_id)))
            except:
                el = None
            if el is not None:
                try:
                    doc.Delete(el.Id)
                except:
                    pass

    new_state, report = sync_schematic(doc, view, desired_controllers, previous_state, cfg)
    manifest_saved, manifest_save_error = save_manifest(view, MANIFEST_PARAM_NAME, new_state)
    view_name = view.Name


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

if controllers_without_address:
    output.print_md(u"### Контроллеры без адреса, пропущены ({})".format(len(controllers_without_address)))
    for name in controllers_without_address:
        output.print_md(u"- {}".format(name))

if group_read_errors:
    output.print_md(u"### Не удалось прочитать состав групп ({})".format(len(group_read_errors)))
    output.print_md(u"У этих типов групп нет ни одного размещённого экземпляра — вставьте группу один раз:")
    for name in group_read_errors:
        output.print_md(u"- {}".format(name))

if report["no_match"]:
    output.print_md(u"### Точки прохода без типовой группы ({})".format(len(report["no_match"])))
    for line in report["no_match"]:
        output.print_md(u"- {}".format(line))

if not manifest_saved:
    output.print_md(
        u"### ⚠ Манифест НЕ сохранён в параметр вида «{}»\n\nПричина: {}.\n\n"
        u"Без него следующий запуск не найдёт эту схему и нарисует всё заново.".format(
            MANIFEST_PARAM_NAME, manifest_save_error)
    )

warn = u"" if manifest_saved else u"\n\nВНИМАНИЕ: манифест не сохранён — см. окно вывода."

forms.alert(
    u"Готово. Вид: {}\n\n"
    u"Точек прохода: не изменилось {} / перерисовано {} / добавлено {} / удалено {}\n"
    u"Контроллеров: добавлено {} / удалено {}\n"
    u"Нерезолвившихся ссылок на схемные элементы: {}\n"
    u"Точек прохода без типовой группы: {}\n"
    u"Контроллеров без адреса (пропущено): {}{}".format(
        view_name,
        report["pp_unchanged"], report["pp_redrawn"], report["pp_created"], report["pp_removed"],
        report["controllers_created"], report["controllers_removed"],
        report["stale_refs"],
        len(report["no_match"]),
        len(controllers_without_address),
        warn,
    )
)

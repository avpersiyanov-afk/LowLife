# -*- coding: utf-8 -*-
__title__ = "Обновить\nсхему"
__doc__ = (
    "Читает JSON-манифест структурной схемы СКУД (создаётся кнопкой "
    "«Структурная схема» рядом с проектом) и обновляет по нему уже "
    "поставленную схему: переносит изменившиеся адреса на схемные "
    "элементы и сообщает о структурных расхождениях (добавленные/"
    "удалённые устройства, изменившийся состав точки прохода — им нужна "
    "полная пересборка)."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import ElementId
from pyrevit import revit, forms, script as pyrevit_script

from lowlife.params import get_string_param, set_param_any
from lowlife.scs_circuits import clean_text_value
from lowlife.skud import collect_controller_devices
from lowlife.skud_schematic import (
    passage_points_of, signature_of, signature_text,
    category_of_from_type_map, invert_category_device_type_ids,
)
from lowlife.skud_schematic_manifest import read_manifest, manifest_path
from lowlife import skud_settings
from lowlife.skud_settings import (
    get_settings_silent, get_schematic_category_device_type_ids,
)

doc = revit.doc
output = pyrevit_script.get_output()

manifest = read_manifest(doc)
if not manifest or not manifest.get("controllers"):
    path, _beside = manifest_path(doc)
    forms.alert(
        u"Манифест структурной схемы не найден или пуст:\n{}\n\n"
        u"Сначала постройте схему кнопкой «Структурная схема».".format(path),
        exitscript=True
    )

settings = get_settings_silent()
skud_settings.require(settings, [
    "controller_workset_keyword", "controller_type_keyword", "workset_param_name",
    "circuit_panel_param", "device_address_param", "schematic_address_param",
])

WORKSET_PARAM_NAME = settings["workset_param_name"]
CONTROLLER_WORKSET_KEYWORD = settings["controller_workset_keyword"]
CONTROLLER_TYPE_KEYWORD = settings["controller_type_keyword"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]
CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
DEVICE_ADDRESS_PARAM = settings["device_address_param"]
PASSAGE_POINT_PARAM = settings.get("passage_point_param") or u""
DEVICE_MARKING_PARAM = settings.get("device_marking_param") or u""
SCHEMATIC_ADDRESS_PARAM = settings["schematic_address_param"]

category_of_real = category_of_from_type_map(
    invert_category_device_type_ids(get_schematic_category_device_type_ids(settings))
)


# ------------------------------------------------------------
# ТЕКУЩЕЕ СОСТОЯНИЕ МОДЕЛИ: {controller_id: {pp_key: (set(real_id), signature)}}
# ------------------------------------------------------------

current_by_controller = {}
for controller, devices in collect_controller_devices(
    doc, WORKSET_PARAM_NAME, CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD,
    CIRCUIT_PANEL_PARAM, EXCLUDED_DEVICE_KEYWORDS
):
    pp_map = {}
    for pp_key, pp_devices in passage_points_of(
        devices, PASSAGE_POINT_PARAM, DEVICE_ADDRESS_PARAM
    ).items():
        sig, _uncat = signature_of(pp_devices, category_of_real)
        pp_map[pp_key] = (set(d.Id.IntegerValue for d in pp_devices), sig)
    current_by_controller[controller.Id.IntegerValue] = pp_map


# ------------------------------------------------------------
# ОБНОВЛЕНИЕ ПО МАНИФЕСТУ
# ------------------------------------------------------------

addr_updates = 0
missing_real = []
missing_schematic = []
rebuild_needed = []

with revit.Transaction("Update SKUD schematic"):
    for c_entry in manifest["controllers"]:
        c_id = c_entry.get("controller_id")
        c_addr = c_entry.get("address", u"")
        live_pps = current_by_controller.get(c_id)

        if live_pps is None:
            rebuild_needed.append(
                u"Контроллер {} (id {}) не найден в модели или больше не подходит "
                u"под фильтр контроллеров.".format(c_addr, c_id)
            )
            live_pps = {}

        for pp_entry in c_entry.get("passage_points", []):
            pp_key = pp_entry.get("key", u"1")
            manifest_ids = set()

            for dev in pp_entry.get("devices", []):
                real_id = dev.get("real_id")
                schem_id = dev.get("schematic_id")
                manifest_ids.add(real_id)

                real_el = doc.GetElement(ElementId(int(real_id))) if real_id else None
                schem_el = doc.GetElement(ElementId(int(schem_id))) if schem_id else None

                if real_el is None:
                    missing_real.append(u"Контроллер {} / ТП {}: устройство id {} удалено из модели.".format(
                        c_addr, pp_key, real_id))
                    continue
                if schem_el is None:
                    missing_schematic.append(u"Контроллер {} / ТП {}: схемный элемент id {} удалён.".format(
                        c_addr, pp_key, schem_id))
                    continue

                new_addr = clean_text_value(get_string_param(real_el, DEVICE_ADDRESS_PARAM)) or u""
                if new_addr != (dev.get("address") or u""):
                    if set_param_any(schem_el, SCHEMATIC_ADDRESS_PARAM, new_addr):
                        addr_updates += 1
                    if DEVICE_MARKING_PARAM:
                        set_param_any(schem_el, DEVICE_MARKING_PARAM, new_addr)

            # структурный дрейф точки прохода
            live = live_pps.get(pp_key)
            if live is None:
                rebuild_needed.append(
                    u"Контроллер {} / ТП {}: в модели этой точки прохода больше нет.".format(c_addr, pp_key))
                continue
            live_ids, live_sig = live
            added = live_ids - manifest_ids
            removed = manifest_ids - live_ids
            if added or removed:
                rebuild_needed.append(
                    u"Контроллер {} / ТП {}: состав изменился (+{} / -{}), сигнатура сейчас {}. "
                    u"Нужна пересборка.".format(
                        c_addr, pp_key, len(added), len(removed), signature_text(live_sig))
                )

        # новые точки прохода, которых нет в манифесте
        manifest_keys = set(pp.get("key", u"1") for pp in c_entry.get("passage_points", []))
        for live_key in live_pps:
            if live_key not in manifest_keys:
                rebuild_needed.append(
                    u"Контроллер {}: в модели появилась точка прохода «{}», её нет в схеме.".format(
                        c_addr, live_key))


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

def _section(title, rows):
    if not rows:
        return
    output.print_md(u"### {} ({})".format(title, len(rows)))
    for r in rows:
        output.print_md(u"- {}".format(r))

_section(u"Устройства удалены из модели", missing_real)
_section(u"Схемные элементы удалены", missing_schematic)
_section(u"Требуется пересборка", rebuild_needed)

forms.alert(
    u"Готово.\n\n"
    u"Адресов обновлено: {}\n"
    u"Устройств удалено из модели: {}\n"
    u"Схемных элементов удалено: {}\n"
    u"Расхождений «нужна пересборка»: {}\n\n"
    u"Подробности — в окне вывода pyRevit.".format(
        addr_updates, len(missing_real), len(missing_schematic), len(rebuild_needed)
    )
)

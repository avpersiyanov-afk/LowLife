# -*- coding: utf-8 -*-
__title__ = "Диагностика\nУстройства схемы"
__doc__ = (
    "Тестовая кнопка: выберите контроллер СКУД на виде. Показывает все его "
    "цепи, все элементы каждой цепи и итоговый список устройств, которые "
    "BuildSkudSchematic поставит на структурную схему — с подсветкой "
    "дублей по ElementId."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import ObjectType
from pyrevit import revit, forms, script as pyrevit_script

from lowlife.params import get_string_param
from lowlife.scs import is_excluded_device, safe_element_name
from lowlife.scs_circuits import norm, clean_text_value
from lowlife.skud_schematic import (
    passage_points_of, signature_of, signature_text,
    category_of_from_type_map, invert_category_device_type_ids,
)

from lowlife import skud_settings
from lowlife.skud_settings import get_settings_silent, get_schematic_category_device_type_ids

doc = revit.doc
uidoc = revit.uidoc
output = pyrevit_script.get_output()


settings = get_settings_silent()

skud_settings.require(settings, [
    "circuit_panel_param", "device_address_param"
])

EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]
CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
DEVICE_ADDRESS_PARAM = settings["device_address_param"]
PASSAGE_POINT_PARAM = settings.get("passage_point_param") or u""

category_of_real = category_of_from_type_map(
    invert_category_device_type_ids(get_schematic_category_device_type_ids(settings))
)


try:
    ref = uidoc.Selection.PickObject(ObjectType.Element, u"Выберите контроллер СКУД")
except:
    forms.alert(u"Операция отменена.", exitscript=True)

controller = doc.GetElement(ref.ElementId)
controller_name = norm(controller.Name)
controller_addr = clean_text_value(get_string_param(controller, DEVICE_ADDRESS_PARAM))

output.print_md(u"### Контроллер: {} (ID {})".format(safe_element_name(controller), controller.Id.IntegerValue))
output.print_md(u"Адрес: `{}`".format(controller_addr))
output.print_md(u"Нормализованное имя (norm): `{}`".format(controller_name))


all_circuits = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
    .WhereElementIsNotElementType() \
    .ToElements()

matching_circuits = []
for c in all_circuits:
    panel_name = norm(get_string_param(c, CIRCUIT_PANEL_PARAM))
    if panel_name == controller_name:
        matching_circuits.append(c)

output.print_md(u"### Цепей с параметром «{}» = «{}»: {}".format(
    CIRCUIT_PANEL_PARAM, controller_name, len(matching_circuits)
))

all_device_ids_flat = []

for c in matching_circuits:
    output.print_md(u"#### Цепь «{}» (ID {})".format(safe_element_name(c), c.Id.IntegerValue))
    try:
        all_elements = list(c.Elements)
    except Exception as ex:
        output.print_md(u"c.Elements FAILED: {}".format(ex))
        continue

    output.print_md(u"Всего элементов в цепи (c.Elements): {}".format(len(all_elements)))
    for el in all_elements:
        is_ctrl = (el.Id == controller.Id)
        is_excl = is_excluded_device(el, EXCLUDED_DEVICE_KEYWORDS) if not is_ctrl else False
        addr = clean_text_value(get_string_param(el, DEVICE_ADDRESS_PARAM))
        tag = []
        if is_ctrl:
            tag.append(u"КОНТРОЛЛЕР (исключается)")
        if is_excl:
            tag.append(u"ИСКЛЮЧЁН по ключевому слову")
        output.print_md(u"  - ID {}: name=`{}` addr=`{}` {}".format(
            el.Id.IntegerValue, safe_element_name(el), addr, u" / ".join(tag)
        ))
        if not is_ctrl and not is_excl:
            all_device_ids_flat.append(el.Id.IntegerValue)


output.print_md(u"### Итог: устройства, которые попадут на схему для этого контроллера")
output.print_md(u"Всего записей в плоском списке (с учётом повторов): {}".format(len(all_device_ids_flat)))

unique_ids = set(all_device_ids_flat)
output.print_md(u"Уникальных ElementId: {}".format(len(unique_ids)))

if len(all_device_ids_flat) != len(unique_ids):
    from collections import Counter
    counts = Counter(all_device_ids_flat)
    dupes = [(eid, cnt) for eid, cnt in counts.items() if cnt > 1]
    output.print_md(u"### ЕСТЬ ДУБЛИКАТЫ ({} id встречаются больше раза)".format(len(dupes)))
    for eid, cnt in dupes:
        el = doc.GetElement(ElementId(eid))
        output.print_md(u"- ID {}: name=`{}` встречается {} раз(а)".format(
            eid, safe_element_name(el) if el else None, cnt
        ))
else:
    output.print_md(u"Дубликатов по ElementId нет.")


# --- разбивка по точкам прохода + сигнатуры (для отладки матчинга групп) ---

unique_devices = []
seen_dev = set()
for eid in all_device_ids_flat:
    if eid in seen_dev:
        continue
    seen_dev.add(eid)
    el = doc.GetElement(ElementId(eid))
    if el is not None:
        unique_devices.append(el)

output.print_md(u"### Точки прохода контроллера (параметр «{}»)".format(
    PASSAGE_POINT_PARAM or u"— не задан, всё → точка прохода 1"))

pps = passage_points_of(unique_devices, PASSAGE_POINT_PARAM, DEVICE_ADDRESS_PARAM)
for pp_key, pp_devices in pps.items():
    sig, uncategorized = signature_of(pp_devices, category_of_real)
    output.print_md(u"#### Точка прохода «{}» — {}".format(pp_key, signature_text(sig)))
    if uncategorized:
        output.print_md(u"  - без категории (не сопоставится): {}".format(uncategorized))
    for d in pp_devices:
        addr = clean_text_value(get_string_param(d, DEVICE_ADDRESS_PARAM))
        cat = category_of_real(d)
        output.print_md(u"  - ID {}: `{}` addr=`{}` категория=`{}`".format(
            d.Id.IntegerValue, safe_element_name(d), addr, cat or u"—"))

forms.alert(u"Готово, смотрите окно вывода pyRevit.")

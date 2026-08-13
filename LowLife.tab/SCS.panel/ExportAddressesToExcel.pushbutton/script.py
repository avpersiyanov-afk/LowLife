# -*- coding: utf-8 -*-
#! python3
__title__ = "Экспорт\nадресов в Excel"
__doc__ = (
    "Выгружает текущие адреса СКС (панели, стояки, узлы маршрута) с "
    "активного вида в xlsx-файл — для передачи таблицы адресации "
    "подрядчику/на ПНР. Читает то, что уже записано в модель кнопкой "
    "«Адреса узлов» (модель не изменяет).\n\n"
    "Работает на движке CPython3 pyRevit и требует пакет openpyxl в его "
    "окружении: py -3 -m pip install openpyxl"
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, ElementId

from pyrevit import revit, forms, script

from lowlife.geometry import get_point
from lowlife.params import get_string_param
from lowlife.scs import classify_element, get_workset_name
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_silent
from lowlife.route_export import export_addressing_to_excel

doc = revit.doc
view = doc.ActiveView

MM_IN_FOOT = 304.8


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

scs_settings.require(settings, [
    "route_type_id", "riser_type_id", "workset_filter_key",
])

ROUTE_TYPE_ID = ElementId(int(settings["route_type_id"]))
RISER_TYPE_ID = ElementId(int(settings["riser_type_id"]))
ADDR_PARAM = settings["addr_param_name"]
ADDR_PREV_PARAM = settings["addr_prev_param_name"]
CABLE_PARAM_NAME = settings["cable_param_name"]
PANEL_KEYWORDS = settings["panel_keywords"]
PANEL_EXCLUDE_KEYWORDS = settings["panel_exclude_keywords"]
WORKSET_PARAM_NAME = settings["workset_param_name"]
WORKSET_FILTER_KEY = settings["workset_filter_key"]

if not ADDR_PARAM or not ADDR_PREV_PARAM:
    forms.alert(
        u"В настройках СКС не заполнены параметры «Адрес узла» / "
        u"«Предыдущий адрес». Запустите кнопку «Параметры СКС».",
        exitscript=True
    )


# ------------------------------------------------------------
# СБОР ЭЛЕМЕНТОВ АКТИВНОГО ВИДА
# ------------------------------------------------------------

collector = FilteredElementCollector(doc, view.Id) \
    .OfCategory(BuiltInCategory.OST_GenericModel) \
    .WhereElementIsNotElementType()

rows = []

for el in collector:
    pt = get_point(el)
    if pt is None:
        continue

    type_id = el.GetTypeId()
    is_route = (type_id == ROUTE_TYPE_ID)
    is_riser = (type_id == RISER_TYPE_ID)
    is_panel = classify_element(
        el, [("panel", PANEL_KEYWORDS, PANEL_EXCLUDE_KEYWORDS)]
    ) == "panel"

    if is_panel and WORKSET_FILTER_KEY:
        ws_name = get_workset_name(el, WORKSET_PARAM_NAME)
        if not ws_name or WORKSET_FILTER_KEY.lower() not in ws_name.lower():
            is_panel = False

    if not (is_route or is_riser or is_panel):
        continue

    category = u"Панель" if is_panel else (u"Стояк" if is_riser else u"Узел маршрута")

    rows.append({
        "id": el.Id.IntegerValue,
        "category": category,
        "x_mm": round(pt.X * MM_IN_FOOT),
        "y_mm": round(pt.Y * MM_IN_FOOT),
        "addr": get_string_param(el, ADDR_PARAM) or u"",
        "addr_prev": get_string_param(el, ADDR_PREV_PARAM) or u"",
        "cable_type": (get_string_param(el, CABLE_PARAM_NAME) or u"") if CABLE_PARAM_NAME else u"",
    })

if not rows:
    forms.alert(
        u"На активном виде не найдено ни одного адресуемого элемента СКС "
        u"(панель/стояк/узел маршрута выбранных типов).",
        exitscript=True
    )

rows.sort(key=lambda r: (r["category"], r["addr"]))


# ------------------------------------------------------------
# СОХРАНЕНИЕ В EXCEL
# ------------------------------------------------------------

out_path = forms.save_file(file_ext='xlsx')
if not out_path:
    script.exit()

try:
    export_addressing_to_excel(rows, out_path)
except ImportError:
    forms.alert(
        u"Не найден пакет openpyxl в CPython-окружении pyRevit.\n\n"
        u"Установите его тем же интерпретатором, что выбран в настройках "
        u"pyRevit (pyRevit -> Settings -> CPython Engine), например:\n"
        u"py -3 -m pip install openpyxl\n\n"
        u"После установки перезапустите Revit.",
        exitscript=True
    )

forms.alert(
    u"Готово.\n\nВыгружено строк: {}\nФайл: {}".format(len(rows), out_path)
)

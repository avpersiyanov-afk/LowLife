# -*- coding: utf-8 -*-
__title__ = "Узлы трассы СКУД"
__doc__ = (
    "Расставляет панели/узлы маршрута/стояки СКУД в точках трассы кабеля. "
    "Узлы СКУД — свои, отдельные от СКС: узлы СКС ведут до шкафа СКС, узлы "
    "СКУД — от устройств до контроллера. Панели/стояки распознаются только "
    "среди элементов рабочего набора СКУД."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife.geometry import get_document_levels
from lowlife.route_nodes import place_route_nodes
from lowlife import skud_settings
from lowlife.skud_settings import get_settings_silent

doc = revit.doc
view = doc.ActiveView


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_silent()

skud_settings.require(settings, [
    "panel_type_id", "route_type_id", "riser_type_id",
    "family_filter", "route_param_value", "route_param_value_riser",
    "device_cable_type_value", "workset_filter_key", "workset_param_name"
])
# Имена параметров (cable_param_name, route_param_name, offset_param_names)
# здесь не проверяются — их наличие/привязку проверяет «Параметры СКУД».

TYPE_ID_BY_CATEGORY = {
    "panel": ElementId(int(settings["panel_type_id"])),
    "route": ElementId(int(settings["route_type_id"])),
    "riser": ElementId(int(settings["riser_type_id"])),
}

symbols_by_category = {}
for category_name, type_id in TYPE_ID_BY_CATEGORY.items():
    symbol = doc.GetElement(type_id)
    if symbol is None:
        forms.alert(
            u"Не найден выбранный тип для категории «{}». "
            u"Откройте «Параметры СКУД» и выберите тип заново.".format(category_name),
            exitscript=True
        )
    symbols_by_category[category_name] = symbol

config = {
    "family_filter": settings["family_filter"],
    "cable_param_name": settings["cable_param_name"],
    "route_param_name": settings["route_param_name"],
    "route_param_value": settings["route_param_value"],
    "route_param_value_riser": settings["route_param_value_riser"],
    "endpoint_cable_type_value": settings["device_cable_type_value"],
    "offset_param_names": settings["offset_param_names"],
    "panel_keywords": settings["panel_keywords"],
    "panel_exclude_keywords": settings["panel_exclude_keywords"],
    "riser_keywords": settings["riser_keywords"],
    "riser_exclude_keywords": settings["riser_exclude_keywords"],
    "workset_param_name": settings["workset_param_name"],
    "workset_filter_key": settings["workset_filter_key"],
}


# ------------------------------------------------------------
# РАССТАНОВКА
# ------------------------------------------------------------

document_levels = get_document_levels(doc)
if not document_levels:
    forms.alert(u"В проекте нет ни одного уровня.", exitscript=True)

with revit.Transaction("Place SKUD Route Nodes"):
    result = place_route_nodes(doc, view, config, symbols_by_category, document_levels)

if not result["segments_found"]:
    forms.alert(
        u"Сегменты трассы не найдены на активном виде.\n\n"
        u"Проверьте фильтр семейства сегментов трассы в «Параметры СКУД» "
        u"(сейчас: «{}»).".format(config["family_filter"]),
        exitscript=True
    )

counts = result["counts_by_category"]

forms.alert(
    u"Готово.\n\n"
    u"Сегментов трассы: {}\n"
    u"Создано элементов: {}\n"
    u"Обновлено элементов: {}\n\n"
    u"Панелей/контроллеров: {}\n"
    u"Стояков: {}\n"
    u"Узлов маршрута: {}".format(
        result["segments_found"],
        len(result["created"]),
        len(result["updated"]),
        counts["panel"],
        counts["riser"],
        counts["route"]
    )
)

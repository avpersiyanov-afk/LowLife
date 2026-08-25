# -*- coding: utf-8 -*-
__title__ = "Маршрут\nцепи"
__doc__ = (
    "Показывает маршрут выбранного шлейфа СПС на модели — для визуальной "
    "проверки топологии (в т.ч. ветвей от изоляторов). Выберите устройство, "
    "входящее в интересующий шлейф (если оно состоит в нескольких цепях — "
    "предложит выбрать нужную из списка). Строит временные линии (Detail "
    "Line на активном виде) по рёбрам дерева шлейфа — панель -> первое "
    "устройство и родитель -> устройство для каждого звена (не непрерывная "
    "цепочка, как у СКС/СКУД: у СПС узлом шлейфа служит само устройство, а "
    "ветви от изоляторов не возвращаются в магистраль) — и выделяет все эти "
    "устройства в модели. Линии временные: при повторном запуске кнопки "
    "(в т.ч. кнопки СКС/СКУД с той же функцией) прошлые линии удаляются."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, ViewType

from pyrevit import revit, forms

from lowlife.geometry import get_point
from lowlife.params import get_string_param
from lowlife.scs_circuits import norm, clean_text_value
from lowlife import fire_alarm_settings
from lowlife.fire_alarm_circuits import find_devices
from lowlife.fire_alarm_loops import parse_route_edges
from lowlife.route_preview import pick_circuit, create_route_line_segments, select_elements

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

if view.ViewType == ViewType.ThreeD:
    forms.alert(
        u"Временная линия маршрута — это Detail Line, она не поддерживается "
        u"на 3D-виде. Переключитесь на план (или другой 2D-вид) и запустите "
        u"кнопку заново.",
        exitscript=True
    )


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

fire_alarm_settings.set_system("SPS")
settings = fire_alarm_settings.get_settings_silent()

fire_alarm_settings.require(settings, [
    "workset_param_name", "workset_filter_key",
    "device_address_param", "circuit_panel_param", "circuit_route_param"
])

CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
CIRCUIT_ROUTE_PARAM = settings["circuit_route_param"]


# ------------------------------------------------------------
# ВЫБОР ЦЕПИ
# ------------------------------------------------------------

picked, circuit = pick_circuit(
    uidoc, doc, u"Выберите устройство, входящее в интересующий шлейф СПС", CIRCUIT_PANEL_PARAM
)


# ------------------------------------------------------------
# РЁБРА МАРШРУТА (ДЕРЕВО ШЛЕЙФА) И ЭЛЕМЕНТЫ ПО АДРЕСАМ
# ------------------------------------------------------------

route_text = clean_text_value(get_string_param(circuit, CIRCUIT_ROUTE_PARAM))
if not route_text:
    forms.alert(
        u"У цепи не заполнен маршрут (параметр «{}»). Сначала запустите "
        u"кнопку «Длины шлейфов» — она считает и записывает маршрут.".format(CIRCUIT_ROUTE_PARAM),
        exitscript=True
    )

edges = parse_route_edges(route_text)

panel_name = norm(get_string_param(circuit, CIRCUIT_PANEL_PARAM))

panel_el = None
if panel_name:
    all_equipment = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
        .WhereElementIsNotElementType() \
        .ToElements()
    for p in all_equipment:
        if norm(p.Name) == panel_name:
            panel_el = p
            break

devices, address_by_id, address_text_by_id, skipped = find_devices(doc, settings)

elements_by_address = {}
for el in devices:
    addr = address_text_by_id.get(el.Id.IntegerValue)
    if addr:
        elements_by_address[addr] = el

segments = []
route_elements = []
seen_ids = set()
missing_addrs = []


def _add_element(el):
    if el is not None and el.Id.IntegerValue not in seen_ids:
        seen_ids.add(el.Id.IntegerValue)
        route_elements.append(el)


for parent_addr, child_addr in edges:
    child_el = elements_by_address.get(child_addr)
    if child_el is None:
        missing_addrs.append(child_addr)
        continue
    child_pt = get_point(child_el)
    _add_element(child_el)

    if parent_addr is None:
        parent_pt = get_point(panel_el) if panel_el is not None else None
        if panel_el is not None:
            _add_element(panel_el)
    else:
        parent_el = elements_by_address.get(parent_addr)
        if parent_el is None:
            missing_addrs.append(parent_addr)
            continue
        parent_pt = get_point(parent_el)
        _add_element(parent_el)

    if parent_pt is not None and child_pt is not None:
        segments.append((parent_pt, child_pt))


# ------------------------------------------------------------
# ПОСТРОЕНИЕ ЛИНИЙ + ВЫДЕЛЕНИЕ
# ------------------------------------------------------------

with revit.Transaction(u"Показать маршрут шлейфа СПС"):
    created_ids = create_route_line_segments(doc, view, segments)

select_elements(uidoc, route_elements, created_ids)

forms.alert(
    u"Готово.\n\n"
    u"Цепь: {}\n"
    u"Устройств/панели в маршруте: {}\n"
    u"Построено отрезков линии: {}\n"
    u"Не найдено устройств по адресу: {}\n\n"
    u"{}"
    u"Устройства и панель выделены в модели.".format(
        norm(circuit.Name) or circuit.Id.IntegerValue,
        len(route_elements),
        len(created_ids),
        len(missing_addrs),
        (u"Не найдены (удалены/на другом виде/вне рабочего набора): {}\n\n".format(
            u", ".join(missing_addrs)
        ) if missing_addrs else u"")
    )
)

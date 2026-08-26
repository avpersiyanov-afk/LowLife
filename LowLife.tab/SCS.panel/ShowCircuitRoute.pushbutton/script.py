# -*- coding: utf-8 -*-
__title__ = "Маршрут\nцепи"
__doc__ = (
    "Показывает маршрут выбранной цепи СКС на модели — для визуальной "
    "проверки, что маршрут выбран правильно. Выберите устройство, входящее "
    "в интересующую цепь (если оно состоит в нескольких цепях — предложит "
    "выбрать нужную из списка). Строит временную линию (Detail Line на "
    "активном виде) через устройство, все узлы/стояки маршрута (по данным "
    "параметра «Маршрут цепи», записанного кнопкой «Расчёт длины цепи») и "
    "панель, и выделяет все эти элементы в модели, чтобы их было видно "
    "отдельно от линии. Вид сам масштабируется, чтобы весь маршрут "
    "поместился целиком. Линия временная: удаляется сама через несколько "
    "секунд, а также при повторном запуске кнопки (в т.ч. кнопки СКУД/СПС "
    "с той же функцией) — прошлая линия удаляется в любом случае."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, ElementId, ViewType

from pyrevit import revit, forms

from lowlife.geometry import get_point
from lowlife.params import get_string_param
from lowlife.scs import is_excluded_device
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_silent
from lowlife.scs_circuits import norm, clean_text_value, parse_route_path
from lowlife.route_preview import pick_circuit, create_route_lines, select_elements, schedule_preview_cleanup, zoom_to_fit_points

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

settings = get_settings_silent()

scs_settings.require(settings, [
    "route_type_id", "riser_type_id", "circuit_panel_param", "circuit_route_param"
])
# addr_param_name здесь не проверяется отдельно — её наличие/привязку в
# проекте проверяет и чинит кнопка «Параметры СКС» (SetupParameters).

ADDR_PARAM = settings["addr_param_name"]
ROUTE_TYPE_ID = ElementId(int(settings["route_type_id"]))
RISER_TYPE_ID = ElementId(int(settings["riser_type_id"]))
CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
CIRCUIT_ROUTE_PARAM = settings["circuit_route_param"]
EXCLUDED_DEVICE_KEYWORDS = settings["excluded_device_keywords"]


# ------------------------------------------------------------
# ВЫБОР ЦЕПИ
# ------------------------------------------------------------

picked, circuit = pick_circuit(
    uidoc, doc, u"Выберите устройство, входящее в интересующую цепь СКС", CIRCUIT_PANEL_PARAM
)


# ------------------------------------------------------------
# ТОЧКИ МАРШРУТА: УСТРОЙСТВО -> УЗЛЫ/СТОЯКИ -> ПАНЕЛЬ
# ------------------------------------------------------------

route_text = clean_text_value(get_string_param(circuit, CIRCUIT_ROUTE_PARAM))
if not route_text:
    forms.alert(
        u"У цепи не заполнен маршрут (параметр «{}»). Сначала запустите "
        u"кнопку «Расчёт длины цепи» — она считает и записывает маршрут.".format(CIRCUIT_ROUTE_PARAM),
        exitscript=True
    )

route_addrs = parse_route_path(route_text)

panel_name = norm(get_string_param(circuit, CIRCUIT_PANEL_PARAM))

panel_el = None
if panel_name:
    all_panels = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
        .WhereElementIsNotElementType() \
        .ToElements()
    for p in all_panels:
        if norm(p.Name) == panel_name:
            panel_el = p
            break

try:
    raw_devs = [x for x in circuit.Elements if panel_el is None or x.Id != panel_el.Id]
except:
    raw_devs = []

normal_devs = [d for d in raw_devs if not is_excluded_device(d, EXCLUDED_DEVICE_KEYWORDS)]
dev_el = normal_devs[0] if normal_devs else picked

nodes_by_addr = {}
all_generic = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_GenericModel) \
    .WhereElementIsNotElementType() \
    .ToElements()

for e in all_generic:
    if e.GetTypeId() not in (ROUTE_TYPE_ID, RISER_TYPE_ID):
        continue
    addr = clean_text_value(get_string_param(e, ADDR_PARAM))
    if addr:
        nodes_by_addr[addr] = e

route_elements = []
if dev_el is not None:
    route_elements.append(dev_el)

missing_addrs = []
for addr in route_addrs:
    el = nodes_by_addr.get(addr)
    if el is None:
        missing_addrs.append(addr)
        continue
    route_elements.append(el)

if panel_el is not None:
    route_elements.append(panel_el)

points = []
for el in route_elements:
    pt = get_point(el)
    if pt is not None:
        points.append(pt)


# ------------------------------------------------------------
# ПОСТРОЕНИЕ ЛИНИИ + ВЫДЕЛЕНИЕ
# ------------------------------------------------------------

with revit.Transaction(u"Показать маршрут цепи СКС"):
    created_ids = create_route_lines(doc, view, points)

select_elements(uidoc, route_elements, created_ids)
zoom_to_fit_points(uidoc, view, points)
schedule_preview_cleanup(uidoc.Application, doc, created_ids)

forms.alert(
    u"Готово.\n\n"
    u"Цепь: {}\n"
    u"Элементов в маршруте: {}\n"
    u"Построено отрезков линии: {}\n"
    u"Не найдено узлов по адресу: {}\n\n"
    u"{}"
    u"Устройство, узлы и панель выделены в модели.".format(
        norm(circuit.Name) or circuit.Id.IntegerValue,
        len(route_elements),
        len(created_ids),
        len(missing_addrs),
        (u"Не найдены (удалены/на другом виде): {}\n\n".format(u", ".join(missing_addrs)) if missing_addrs else u"")
    )
)

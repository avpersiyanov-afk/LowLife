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
    "отдельно от линии. Линии временные: при повторном запуске кнопки "
    "прошлые линии (созданные ею же) удаляются."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter, ElementId, Line, ViewType
)
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

from pyrevit import revit, forms

from lowlife.geometry import get_point
from lowlife.params import get_string_param
from lowlife.scs import is_excluded_device
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_silent
from lowlife.scs_circuits import norm, clean_text_value, parse_route_path

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

# Метка во встроенном параметре "Комментарии" временных линий этой кнопки
# (BuiltInParameter, а не имя параметра текстом — чтобы поиск/удаление
# прошлых линий не зависел от языка интерфейса Revit).
MARKER_TEXT = u"LowLife_SCS_RoutePreview"


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
# УДАЛЕНИЕ ПРОШЛЫХ ВРЕМЕННЫХ ЛИНИЙ ЭТОЙ КНОПКИ (на активном виде)
# ------------------------------------------------------------

old_line_ids = []
for e in FilteredElementCollector(doc, view.Id).OfCategory(BuiltInCategory.OST_Lines).WhereElementIsNotElementType():
    try:
        p = e.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if p and p.HasValue and p.AsString() == MARKER_TEXT:
            old_line_ids.append(e.Id)
    except:
        continue


# ------------------------------------------------------------
# ВЫБОР ЦЕПИ
# ------------------------------------------------------------

try:
    ref = uidoc.Selection.PickObject(
        ObjectType.Element,
        u"Выберите устройство, входящее в интересующую цепь СКС"
    )
except OperationCanceledException:
    forms.alert(u"Операция отменена.", exitscript=True)
    ref = None

picked = doc.GetElement(ref)

mep_model = getattr(picked, "MEPModel", None)
systems = []
if mep_model is not None:
    try:
        systems = list(mep_model.GetElectricalSystems())
    except:
        systems = []

if not systems:
    forms.alert(
        u"У выбранного элемента нет электрических цепей (или это не "
        u"устройство, а, например, узел маршрута/панель). Выберите "
        u"устройство, подключённое к цепи СКС.",
        exitscript=True
    )

if len(systems) == 1:
    circuit = systems[0]
else:
    labels = []
    by_label = {}
    for s in systems:
        label = u"{} — {} (ID {})".format(
            norm(get_string_param(s, CIRCUIT_PANEL_PARAM)) or u"без панели",
            norm(s.Name) or u"?",
            s.Id.IntegerValue
        )
        labels.append(label)
        by_label[label] = s

    selected_label = forms.SelectFromList.show(
        labels,
        title=u"У устройства несколько цепей — выберите нужную",
        button_name=u"Показать",
        multiselect=False
    )
    if not selected_label:
        forms.alert(u"Операция отменена.", exitscript=True)
    circuit = by_label[selected_label]


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

created_ids = []

with revit.Transaction(u"Показать маршрут цепи СКС"):
    if old_line_ids:
        ids_to_delete = List[ElementId]()
        for eid in old_line_ids:
            ids_to_delete.Add(eid)
        try:
            doc.Delete(ids_to_delete)
        except:
            pass

    for i in range(len(points) - 1):
        try:
            line = Line.CreateBound(points[i], points[i + 1])
        except:
            continue
        try:
            curve_el = doc.Create.NewDetailCurve(view, line)
        except:
            continue

        try:
            p = curve_el.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p and not p.IsReadOnly:
                p.Set(MARKER_TEXT)
        except:
            pass

        created_ids.append(curve_el.Id)

selection_ids = List[ElementId]()
for el in route_elements:
    selection_ids.Add(el.Id)
for eid in created_ids:
    selection_ids.Add(eid)

try:
    uidoc.Selection.SetElementIds(selection_ids)
except:
    pass

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

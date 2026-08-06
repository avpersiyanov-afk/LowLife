# -*- coding: utf-8 -*-

__title__ = "Журнал\nцепей"
__doc__ = "Формирует журнал электрических цепей и сохраняет в CSV-файл."
__author__ = "Pipers"

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('System.Windows.Forms')

import io
import System
from System.Collections.Generic import IList
from System.Windows.Forms import SaveFileDialog, DialogResult

from Autodesk.Revit.DB import BuiltInCategory, BuiltInParameter, StorageType, ElementId, UnitTypeId
from Autodesk.Revit.DB import FilteredElementCollector

from pyrevit import revit, forms

from lowlife.cable_schedule import (
    get_sorted_loads, get_route_entity, circuit_is_valid, get_mark,
    to_meters, load_settings,
)

doc = revit.doc

HEADERS = [
    u"№ п/п", u"Обозначение кабеля, провода", u"Начало", u"Конец",
    u"Марка кабеля, провода", u"Количество кусков кабеля", u"Длина, м",
    u"Код способа прокладки (см. примечание)", u"Общая длина, м",
]

KNS_NAMES = [u"Гофра (кондуит)", u"Лоток (кабельный)", u"Короб (воздуховод)"]

# BuiltInParameter без публичного имени в этой версии API — соответствует
# оригинальному C#-плагину (-1006900): текстовый параметр помещения/зоны,
# аналог имени пространства (Space Name).
_SPACE_NAME_PARAM = System.Enum.ToObject(BuiltInParameter, -1006900)

# Классификация КНС для журнала: 0=Гофра/кондуит, 1=Лоток, 2=Короб.
# Соответствует оригинальному C#-плагину (GetKnsCategory).
_KNS_CATEGORY_IDS = {
    int(BuiltInCategory.OST_Conduit): 0,
    int(BuiltInCategory.OST_ConduitFitting): 0,
    int(BuiltInCategory.OST_CableTray): 1,
    int(BuiltInCategory.OST_CableTrayFitting): 1,
    int(BuiltInCategory.OST_DuctCurves): 2,
    int(BuiltInCategory.OST_DuctFitting): 2,
}


def get_space(spaces, elem):
    if elem is None:
        return None
    loc = elem.Location
    pt = getattr(loc, "Point", None)
    if pt is None:
        return None
    for s in spaces:
        try:
            if s.IsPointInSpace(pt):
                return s
        except:
            pass
    return None


def build_location(spaces, elem):
    if elem is None:
        return u""

    parts = []

    if elem.LevelId is not None and elem.LevelId.IntegerValue != -1:
        level = doc.GetElement(elem.LevelId)
        if level is not None:
            parts.append(level.Name)

    space = get_space(spaces, elem)
    space_name = u""
    if space is not None:
        p = space.get_Parameter(_SPACE_NAME_PARAM)
        space_name = (p.AsString() or u"") if p else u""
    space_number = space.Number if space is not None else u""

    if space_name:
        parts.append(space_name)
    if space_number:
        parts.append(space_number)

    mark = get_mark(elem)
    if mark and mark != u"?":
        parts.append(mark)

    return u", ".join(parts)


def get_cable_mark(circuit, param_name):
    if not param_name or not param_name.strip():
        return u""
    p = circuit.LookupParameter(param_name)
    if p is None:
        return u""
    if p.StorageType == StorageType.String:
        return p.AsString() or u""
    return p.AsValueString() or u""


def get_kns_category(seg_id):
    if seg_id is None or seg_id == ElementId.InvalidElementId:
        return -1
    elem = doc.GetElement(seg_id)
    if elem is None or elem.Category is None:
        return -1
    return _KNS_CATEGORY_IDS.get(elem.Category.Id.IntegerValue, -1)


def escape_csv(value):
    if not value:
        return u""
    if u";" in value or u'"' in value or u"\n" in value or u"\r" in value:
        return u'"' + value.replace(u'"', u'""') + u'"'
    return value


def to_csv_line(cells):
    return u";".join(escape_csv(c) for c in cells)


def write_csv(file_path, rows):
    with io.open(file_path, "w", encoding="utf-8-sig") as f:
        f.write(to_csv_line(HEADERS) + u"\r\n")
        for i, row in enumerate(rows, start=1):
            f.write(to_csv_line([str(i)] + row) + u"\r\n")
        f.write(u"\r\n")
        f.write(u"Примечание — коды способов прокладки:\r\n")
        for i, name in enumerate(KNS_NAMES):
            f.write(to_csv_line([u"[{}]".format(i), name]) + u"\r\n")


settings = load_settings()
cable_mark_param = settings.get("cable_mark_parameter", u"")

circuits = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
    .WhereElementIsNotElementType() \
    .ToElements()
circuits = [c for c in circuits if c.BaseEquipment is not None]

if doc.IsWorkshared:
    active_workset_id = doc.GetWorksetTable().GetActiveWorksetId()
    circuits = [c for c in circuits if c.WorksetId.IntegerValue == active_workset_id.IntegerValue]

if not circuits:
    forms.alert(u"Нет электрических цепей для экспорта.", title=u"Журнал цепей", exitscript=True)

spaces = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_MEPSpaces)
    .WhereElementIsNotElementType()
    .ToElements()
)

rows = []

for circuit in circuits:
    sorted_loads = get_sorted_loads(circuit)
    if not sorted_loads:
        continue

    base_equipment = circuit.BaseEquipment
    first_load = sorted_loads[0]

    route_entity = get_route_entity(circuit)
    route_valid = route_entity is not None and circuit_is_valid(circuit, route_entity, sorted_loads)

    row = []
    mark_base = get_mark(base_equipment)
    mark_load = get_mark(first_load)
    row.append(u"{} - {}".format(mark_base, mark_load))
    row.append(build_location(spaces, base_equipment))
    row.append(build_location(spaces, first_load))
    row.append(get_cable_mark(circuit, cable_mark_param))
    row.append(u"1")

    if route_valid:
        seg_elements = list(route_entity.Get[IList[ElementId]]("segmentWayElement"))
        seg_lengths = list(route_entity.Get[IList[float]]("segmentWayLength", UnitTypeId.Millimeters))

        totals = [0.0, 0.0, 0.0]
        for i in range(len(seg_elements)):
            if seg_elements[i] == first_load.Id:
                break
            length_mm = seg_lengths[i]
            if length_mm > 0.0:
                kns_cat = get_kns_category(seg_elements[i])
                if kns_cat >= 0:
                    totals[kns_cat] += length_mm

        length_cells = []
        code_cells = []
        for i in range(3):
            if totals[i] > 0.0:
                length_cells.append(u"{:.1f}".format(round(totals[i] / 1000.0, 1)))
                code_cells.append(u"[{}]".format(i))

        row.append(u"; ".join(length_cells))
        row.append(u"; ".join(code_cells))
        row.append(u"{:.1f}".format(round(sum(totals) / 1000.0, 1)))
    else:
        length_m = u"{:.1f}".format(round(to_meters(circuit.Length), 1))
        row.append(length_m)
        row.append(u"—")
        row.append(length_m)

    rows.append(row)

if not rows:
    forms.alert(u"Нет данных для экспорта.", title=u"Журнал цепей", exitscript=True)

rows.sort(key=lambda r: r[0].lower())

dialog = SaveFileDialog()
dialog.Title = u"Сохранить журнал цепей"
dialog.Filter = u"CSV файл (*.csv)|*.csv"
dialog.FileName = u"Журнал_цепей.csv"

if dialog.ShowDialog() == DialogResult.OK:
    write_csv(dialog.FileName, rows)
    forms.alert(
        u"Экспортировано строк: {}\nСохранено: {}".format(len(rows), dialog.FileName),
        title=u"Журнал цепей"
    )

# -*- coding: utf-8 -*-

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms


doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

# Отступ размерной линии от осей, мм
OFFSET_MM = 1000.0

MM_IN_FOOT = 304.8
OFFSET = OFFSET_MM / MM_IN_FOOT


# ------------------------------------------------------------
# ФУНКЦИИ
# ------------------------------------------------------------

def get_dim_type_name(dim_type):
    """Получить имя типа размера"""
    try:
        param = dim_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if param:
            return param.AsString()
    except:
        pass

    try:
        return dim_type.Name
    except:
        return str(dim_type.Id.IntegerValue)


class DimTypeOption(object):
    """Обертка для красивого отображения типа размера в окне выбора"""

    def __init__(self, dim_type):
        self.dim_type = dim_type
        self.name = get_dim_type_name(dim_type)

    def __str__(self):
        return self.name


def get_selected_grids():
    """Получить выбранные оси"""
    selected_ids = uidoc.Selection.GetElementIds()

    grids = []

    for el_id in selected_ids:
        el = doc.GetElement(el_id)
        if isinstance(el, Grid):
            grids.append(el)

    return grids


def get_linear_dimension_types():
    """Получить линейные стили размеров"""
    result = []

    collector = FilteredElementCollector(doc).OfClass(DimensionType)

    for dim_type in collector:
        try:
            if dim_type.StyleType == DimensionStyleType.Linear:
                result.append(dim_type)
        except:
            pass

    return result


def choose_dimension_type():
    """Окно выбора стиля размеров"""
    dim_types = get_linear_dimension_types()

    if not dim_types:
        forms.alert(
            "В проекте не найдены линейные стили размеров.",
            exitscript=True
        )

    options = [DimTypeOption(x) for x in dim_types]
    options = sorted(options, key=lambda x: x.name)

    selected = forms.SelectFromList.show(
        options,
        title="Выберите стиль размеров",
        button_name="Создать размеры",
        multiselect=False
    )

    if not selected:
        forms.alert("Операция отменена.", exitscript=True)

    return selected.dim_type


def is_vertical_grid(grid):
    """
    Определяет направление оси.

    True  — вертикальная ось
    False — горизонтальная ось
    """
    curve = grid.Curve

    p1 = curve.GetEndPoint(0)
    p2 = curve.GetEndPoint(1)

    dx = abs(p2.X - p1.X)
    dy = abs(p2.Y - p1.Y)

    return dy >= dx


def sort_grids(grids, vertical):
    """Сортировка осей"""

    def key_func(grid):
        curve = grid.Curve
        p1 = curve.GetEndPoint(0)
        p2 = curve.GetEndPoint(1)

        if vertical:
            return (p1.X + p2.X) / 2.0
        else:
            return (p1.Y + p2.Y) / 2.0

    return sorted(grids, key=key_func)


def create_dimension_chain(grids, vertical, dim_type):
    """Создать размерную цепочку по осям"""

    if len(grids) < 2:
        return None

    refs = ReferenceArray()

    for grid in grids:
        refs.Append(Reference(grid))

    points = []

    for grid in grids:
        curve = grid.Curve
        points.append(curve.GetEndPoint(0))
        points.append(curve.GetEndPoint(1))

    z = points[0].Z

    if vertical:
        # Вертикальные оси образмериваются горизонтальной размерной линией

        x_values = []

        for grid in grids:
            curve = grid.Curve
            p1 = curve.GetEndPoint(0)
            p2 = curve.GetEndPoint(1)
            x_values.append((p1.X + p2.X) / 2.0)

        y_min = min([p.Y for p in points])
        y_dim = y_min - OFFSET

        start = XYZ(min(x_values), y_dim, z)
        end = XYZ(max(x_values), y_dim, z)

    else:
        # Горизонтальные оси образмериваются вертикальной размерной линией

        y_values = []

        for grid in grids:
            curve = grid.Curve
            p1 = curve.GetEndPoint(0)
            p2 = curve.GetEndPoint(1)
            y_values.append((p1.Y + p2.Y) / 2.0)

        x_min = min([p.X for p in points])
        x_dim = x_min - OFFSET

        start = XYZ(x_dim, min(y_values), z)
        end = XYZ(x_dim, max(y_values), z)

    dim_line = Line.CreateBound(start, end)

    # Сначала создаем размер стандартным типом
    dimension = doc.Create.NewDimension(view, dim_line, refs)

    # Потом меняем на выбранный стиль
    if dim_type:
        dimension.ChangeTypeId(dim_type.Id)

    return dimension


# ------------------------------------------------------------
# ОСНОВНОЙ КОД
# ------------------------------------------------------------

grids = get_selected_grids()

if not grids:
    forms.alert(
        "Сначала выберите оси в Revit, потом запустите кнопку.",
        exitscript=True
    )

if len(grids) < 2:
    forms.alert(
        "Выберите минимум две оси.",
        exitscript=True
    )

dim_type = choose_dimension_type()

vertical_grids = []
horizontal_grids = []

for grid in grids:
    if is_vertical_grid(grid):
        vertical_grids.append(grid)
    else:
        horizontal_grids.append(grid)

created = []

with revit.Transaction("Create Grid Dimensions"):

    if len(vertical_grids) >= 2:
        vertical_grids = sort_grids(vertical_grids, True)
        dim = create_dimension_chain(vertical_grids, True, dim_type)

        if dim:
            created.append(dim)

    if len(horizontal_grids) >= 2:
        horizontal_grids = sort_grids(horizontal_grids, False)
        dim = create_dimension_chain(horizontal_grids, False, dim_type)

        if dim:
            created.append(dim)


forms.alert(
    "Готово.\n\nСоздано размерных цепочек: {}".format(len(created))
)

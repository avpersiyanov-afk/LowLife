# -*- coding: utf-8 -*-

import clr

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

from pyrevit import revit, DB, forms


doc = revit.doc
uidoc = revit.uidoc
active_view = doc.ActiveView


# ============================================================
# НАСТРОЙКИ ПО УМОЛЧАНИЮ, мм
# ============================================================

DEFAULT_OFFSET_MM = 1000.0
DEFAULT_GAP_MM = 700.0


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def mm_to_ft(value_mm):
    return float(value_mm) / 304.8


def get_element_name(el):
    try:
        return Element.Name.GetValue(el)
    except:
        try:
            return el.Name
        except:
            return str(el.Id.IntegerValue)


class GridSelectionFilter(ISelectionFilter):
    def AllowElement(self, element):
        return isinstance(element, Grid)

    def AllowReference(self, reference, position):
        return False


def get_selected_grids():
    """
    Получает оси из текущего выбора.
    Если ничего не выбрано — предлагает выбрать оси вручную.
    """

    selected_ids = list(uidoc.Selection.GetElementIds())
    selected_elements = [doc.GetElement(el_id) for el_id in selected_ids]

    grids = [el for el in selected_elements if isinstance(el, Grid)]

    if grids:
        return grids

    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element,
            GridSelectionFilter(),
            "Выберите оси"
        )
        grids = [doc.GetElement(r.ElementId) for r in refs]
        return grids
    except:
        return []


def get_grid_direction(grid):
    """
    True  = вертикальная ось
    False = горизонтальная ось
    """

    curve = grid.Curve
    sp = curve.GetEndPoint(0)
    ep = curve.GetEndPoint(1)

    dx = abs(ep.X - sp.X)
    dy = abs(ep.Y - sp.Y)

    return dy > dx


def get_sorted_grids(grids, is_vertical):
    """
    Сортирует оси по координате.
    Вертикальные — по X.
    Горизонтальные — по Y.
    """

    def sort_key(grid):
        curve = grid.Curve
        sp = curve.GetEndPoint(0)
        ep = curve.GetEndPoint(1)

        if is_vertical:
            return (sp.X + ep.X) / 2.0
        else:
            return (sp.Y + ep.Y) / 2.0

    return sorted(grids, key=sort_key)


def get_linear_dimension_types(doc):
    """
    Возвращает все линейные типы размеров.
    """

    dim_types = []

    collector = FilteredElementCollector(doc).OfClass(DimensionType)

    for dt in collector:
        try:
            if dt.StyleType == DimensionStyleType.Linear:
                dim_types.append(dt)
        except:
            pass

    return dim_types


def show_settings_window():
    """
    Окно настроек pyRevit:
    - выбор типа размера;
    - отступ цепочки;
    - отступ общего размера.
    """

    dim_types = get_linear_dimension_types(doc)

    if not dim_types:
        forms.alert(
            "В проекте не найдены линейные типы размеров.",
            exitscript=True
        )

    dim_type_options = {}

    for dt in dim_types:
        name = get_element_name(dt)
        dim_type_options[name] = dt

    components = [
        forms.Label("Стиль размеров:"),
        forms.ComboBox("dim_type", dim_type_options),

        forms.Separator(),

        forms.Label("Отступ цепочки размеров от осей, мм:"),
        forms.TextBox("offset_mm", str(DEFAULT_OFFSET_MM)),

        forms.Label("Отступ общего размера от цепочки, мм:"),
        forms.TextBox("gap_mm", str(DEFAULT_GAP_MM)),

        forms.Separator(),

        forms.Button("Создать размеры")
    ]

    form = forms.FlexForm("Настройки размеров по осям", components)
    form.show()

    if not form.values:
        return None

    try:
        offset_mm = float(str(form.values["offset_mm"]).replace(",", "."))
        gap_mm = float(str(form.values["gap_mm"]).replace(",", "."))
    except:
        forms.alert(
            "Некорректно указаны отступы. Нужно вводить числа в миллиметрах.",
            exitscript=True
        )

    settings = {
        "dim_type": form.values["dim_type"],
        "offset": mm_to_ft(offset_mm),
        "gap": mm_to_ft(gap_mm)
    }

    return settings


def create_chain_dimension(grids, is_vertical, view, offset, dim_type):
    """
    Создает цепочку размеров на все выбранные оси.
    """

    if len(grids) < 2:
        return None

    ref_array = ReferenceArray()

    for grid in grids:
        ref_array.Append(Reference(grid))

    all_points = []

    for grid in grids:
        c = grid.Curve
        all_points.append(c.GetEndPoint(0))
        all_points.append(c.GetEndPoint(1))

    if is_vertical:
        x_coords = [
            (g.Curve.GetEndPoint(0).X + g.Curve.GetEndPoint(1).X) / 2.0
            for g in grids
        ]

        y_min = min(p.Y for p in all_points)
        y_line = y_min - offset

        p1 = XYZ(min(x_coords), y_line, 0)
        p2 = XYZ(max(x_coords), y_line, 0)

    else:
        y_coords = [
            (g.Curve.GetEndPoint(0).Y + g.Curve.GetEndPoint(1).Y) / 2.0
            for g in grids
        ]

        x_min = min(p.X for p in all_points)
        x_line = x_min - offset

        p1 = XYZ(x_line, min(y_coords), 0)
        p2 = XYZ(x_line, max(y_coords), 0)

    line = Line.CreateBound(p1, p2)

    if dim_type:
        return doc.Create.NewDimension(view, line, ref_array, dim_type)
    else:
        return doc.Create.NewDimension(view, line, ref_array)


def create_total_dimension(grids, is_vertical, view, offset, dim_type):
    """
    Создает общий размер между первой и последней осью.
    """

    if len(grids) < 3:
        return None

    first = grids[0]
    last = grids[-1]

    ref_array = ReferenceArray()
    ref_array.Append(Reference(first))
    ref_array.Append(Reference(last))

    all_points = []

    for grid in grids:
        c = grid.Curve
        all_points.append(c.GetEndPoint(0))
        all_points.append(c.GetEndPoint(1))

    if is_vertical:
        x1 = (first.Curve.GetEndPoint(0).X + first.Curve.GetEndPoint(1).X) / 2.0
        x2 = (last.Curve.GetEndPoint(0).X + last.Curve.GetEndPoint(1).X) / 2.0

        y_min = min(p.Y for p in all_points)
        y_line = y_min - offset

        p1 = XYZ(x1, y_line, 0)
        p2 = XYZ(x2, y_line, 0)

    else:
        y1 = (first.Curve.GetEndPoint(0).Y + first.Curve.GetEndPoint(1).Y) / 2.0
        y2 = (last.Curve.GetEndPoint(0).Y + last.Curve.GetEndPoint(1).Y) / 2.0

        x_min = min(p.X for p in all_points)
        x_line = x_min - offset

        p1 = XYZ(x_line, y1, 0)
        p2 = XYZ(x_line, y2, 0)

    line = Line.CreateBound(p1, p2)

    if dim_type:
        return doc.Create.NewDimension(view, line, ref_array, dim_type)
    else:
        return doc.Create.NewDimension(view, line, ref_array)


# ============================================================
# ОСНОВНАЯ ЛОГИКА
# ============================================================

grids = get_selected_grids()

if not grids:
    forms.alert(
        "Оси не выбраны.",
        exitscript=True
    )

settings = show_settings_window()

if not settings:
    forms.alert(
        "Операция отменена.",
        exitscript=True
    )

dim_type = settings["dim_type"]
offset = settings["offset"]
gap = settings["gap"]

vertical = [g for g in grids if get_grid_direction(g)]
horizontal = [g for g in grids if not get_grid_direction(g)]

created_chain = []
created_total = []

t = Transaction(doc, "Создать размеры по осям")
t.Start()

try:
    # Вертикальные оси
    if len(vertical) >= 2:
        v_sorted = get_sorted_grids(vertical, True)

        dim_v = create_chain_dimension(
            v_sorted,
            True,
            active_view,
            offset,
            dim_type
        )

        if dim_v:
            created_chain.append(dim_v)

        dim_v_total = create_total_dimension(
            v_sorted,
            True,
            active_view,
            offset + gap,
            dim_type
        )

        if dim_v_total:
            created_total.append(dim_v_total)

    # Горизонтальные оси
    if len(horizontal) >= 2:
        h_sorted = get_sorted_grids(horizontal, False)

        dim_h = create_chain_dimension(
            h_sorted,
            False,
            active_view,
            offset,
            dim_type
        )

        if dim_h:
            created_chain.append(dim_h)

        dim_h_total = create_total_dimension(
            h_sorted,
            False,
            active_view,
            offset + gap,
            dim_type
        )

        if dim_h_total:
            created_total.append(dim_h_total)

    t.Commit()

except Exception as ex:
    t.RollBack()

    forms.alert(
        "Ошибка при создании размеров:\n\n{}".format(str(ex)),
        exitscript=True
    )


forms.alert(
    "Готово.\n\n"
    "Цепочек размеров: {}\n"
    "Общих размеров: {}\n"
    "Вертикальных осей: {}\n"
    "Горизонтальных осей: {}".format(
        len(created_chain),
        len(created_total),
        len(vertical),
        len(horizontal)
    )
)

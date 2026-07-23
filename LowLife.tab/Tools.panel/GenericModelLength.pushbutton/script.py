# -*- coding: utf-8 -*-

__title__ = "Длина линий"
__doc__ = "Сумма длин выбранных обобщённых моделей по типам"
__author__ = "Pipers"

from pyrevit import revit, DB, forms

from System.Windows import Window, WindowStyle, WindowStartupLocation, SizeToContent, Thickness
from System.Windows.Controls import StackPanel, TextBlock, Border
from System.Windows.Media import Brushes
from System.Windows import CornerRadius


doc = revit.doc
selection = revit.get_selection()

generic_cat_id = DB.ElementId(DB.BuiltInCategory.OST_GenericModel)


def show_click_window(text):
    """
    Маленькое окно без крестика.
    Закрывается кликом мыши по окну.
    """
    win = Window()
    win.Title = "Результат"
    win.WindowStyle = WindowStyle.None
    win.SizeToContent = SizeToContent.WidthAndHeight
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    win.Topmost = True
    win.ResizeMode = 0

    border = Border()
    border.Background = Brushes.White
    border.BorderBrush = Brushes.Gray
    border.BorderThickness = Thickness(1)
    border.CornerRadius = CornerRadius(6)
    border.Padding = Thickness(18)

    panel = StackPanel()

    title = TextBlock()
    title.Text = "Длина по типам"
    title.FontSize = 16
    title.FontWeight = 700
    title.Margin = Thickness(0, 0, 0, 10)

    body = TextBlock()
    body.Text = text
    body.FontSize = 14
    body.TextWrapping = 1

    hint = TextBlock()
    hint.Text = "\nНажмите мышью, чтобы закрыть"
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray

    panel.Children.Add(title)
    panel.Children.Add(body)
    panel.Children.Add(hint)

    border.Child = panel
    win.Content = border

    def close_window(sender, args):
        win.Close()

    win.MouseDown += close_window

    win.ShowDialog()


def get_type_name(el):
    type_id = el.GetTypeId()

    if type_id and type_id != DB.ElementId.InvalidElementId:
        type_el = doc.GetElement(type_id)

        if type_el:
            p = type_el.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
            if p and p.HasValue:
                return p.AsString()

            try:
                return type_el.Name
            except:
                return "Тип ID {}".format(type_el.Id.IntegerValue)

    return "Без типа"


def get_length(el):
    loc = el.Location

    if isinstance(loc, DB.LocationCurve):
        return loc.Curve.Length

    p = el.LookupParameter("Длина") or el.LookupParameter("Length") or el.LookupParameter("L")

    if p and p.HasValue and p.StorageType == DB.StorageType.Double:
        return p.AsDouble()

    type_id = el.GetTypeId()
    if type_id and type_id != DB.ElementId.InvalidElementId:
        type_el = doc.GetElement(type_id)

        if type_el:
            p = type_el.LookupParameter("Длина") or type_el.LookupParameter("Length") or type_el.LookupParameter("L")

            if p and p.HasValue and p.StorageType == DB.StorageType.Double:
                return p.AsDouble()

    return 0.0


try:
    selected = list(selection.elements)
except:
    selected = list(selection)


if not selected:
    show_click_window("Сначала выберите обобщённые модели.")
else:
    totals = {}

    for el in selected:
        if not el.Category:
            continue

        if el.Category.Id.IntegerValue != generic_cat_id.IntegerValue:
            continue

        type_name = get_type_name(el)
        length_ft = get_length(el)

        if type_name not in totals:
            totals[type_name] = 0.0

        totals[type_name] += length_ft

    if not totals:
        show_click_window("Среди выбранных элементов нет обобщённых моделей.")
    else:
        total_ft = sum(totals.values())

        lines = []

        for type_name in sorted(totals.keys()):
            length_m = totals[type_name] * 0.3048
            lines.append("{} - {:.2f} м".format(type_name, length_m))

        lines.append("")
        lines.append("Общая длина - {:.2f} м".format(total_ft * 0.3048))

        show_click_window("\n".join(lines))

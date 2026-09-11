# -*- coding: utf-8 -*-

__title__ = u"Фильтр\nвыбора"
__doc__ = (
    u"Выделение элементов на активном виде, ограниченное только нужными "
    u"категориями. По кнопке показывается список категорий, которые есть "
    u"на активном виде (с числом элементов в каждой) — отметьте галочками "
    u"нужные и нажмите «Выбрать». После этого выделяйте элементы кликом "
    u"и/или рамкой: в выделение попадут только элементы отмеченных "
    u"категорий, остальные рамкой не подхватываются. Нажмите Enter (или "
    u"ПКМ -> «Готово»), чтобы завершить — выделение останется активным в "
    u"Revit после закрытия инструмента."
)
__author__ = "Pipers"

from Autodesk.Revit.DB import ElementId
from System.Collections.Generic import List

from pyrevit import revit, forms

from lowlife.selection import list_view_categories, pick_elements_by_categories

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView


# ------------------------------------------------------------
# ОСНОВНОЙ СЦЕНАРИЙ
# ------------------------------------------------------------

options = list_view_categories(doc, view)

if not options:
    forms.alert(
        u"На активном виде нет модельных элементов, по которым можно "
        u"фильтровать выбор.",
        title=u"Фильтр выбора",
        exitscript=True
    )

chosen = forms.SelectFromList.show(
    options,
    title=u"Категории для выбора (можно несколько)",
    button_name=u"Выбрать",
    multiselect=True
)

if not chosen:
    forms.alert(u"Категории не выбраны — операция отменена.", exitscript=True)

category_ids = set(o.category_id.IntegerValue for o in chosen)

elements = pick_elements_by_categories(uidoc, doc, category_ids)

# Явно фиксируем выбор как текущее выделение Revit, чтобы оно осталось
# активным (подсветка, панель «Свойства») после завершения инструмента —
# сами по себе результаты PickObjects этого не гарантируют.
ids = List[ElementId]()
for el in elements:
    ids.Add(el.Id)
uidoc.Selection.SetElementIds(ids)

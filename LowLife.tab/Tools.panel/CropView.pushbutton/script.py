# -*- coding: utf-8 -*-

__title__ = u"Обрезать\nвид"
__doc__ = (
    u"Обрезает активный вид и аннотации по прямоугольнику: укажите мышью "
    u"два противоположных угла — по ним задаётся рамка подрезки вида, "
    u"включаются подрезка вида и подрезка аннотаций (с минимальным отступом "
    u"от рамки). Работает на планах, разрезах, фасадах и узлах. Esc — отмена."
)
__author__ = "Pipers"

import traceback

from Autodesk.Revit.DB import Transaction, TransactionGroup
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms

from lowlife import view_crop

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

TITLE = u"Обрезать вид"


reason = view_crop.unsupported_reason(view)
if reason:
    forms.alert(reason, title=TITLE, exitscript=True)

group = TransactionGroup(doc, TITLE)
group.Start()
try:
    # PickPoint требует рабочую плоскость; на разрезах/фасадах её часто нет.
    t = Transaction(doc, u"Рабочая плоскость вида")
    t.Start()
    view_crop.ensure_work_plane(doc, view)
    t.Commit()

    pt1 = uidoc.Selection.PickPoint(u"Обрезать вид: первый угол рамки")
    pt2 = uidoc.Selection.PickPoint(u"Обрезать вид: противоположный угол рамки")

    t = Transaction(doc, TITLE)
    t.Start()
    warnings = view_crop.apply_crop(view, pt1, pt2)
    t.Commit()
    group.Assimilate()
except OperationCanceledException:
    group.RollBack()
except ValueError as err:
    group.RollBack()
    forms.alert(unicode(err), title=TITLE)
except Exception:
    group.RollBack()
    forms.alert(u"Не удалось обрезать вид (возможно, подрезка задана "
                u"шаблоном вида).\n\n" + traceback.format_exc(), title=TITLE)
else:
    if warnings:
        forms.alert(u"\n".join(warnings), title=TITLE)

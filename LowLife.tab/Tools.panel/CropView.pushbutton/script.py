# -*- coding: utf-8 -*-

__title__ = u"Обрезать\nвид"
__doc__ = (
    u"Обрезает вид и аннотации по прямоугольнику: укажите мышью два "
    u"противоположных угла, затем выберите, что обрезать — этот вид или его "
    u"копию (простую, с детализацией или зависимую; в конец имени копии "
    u"добавляется текст). Включаются подрезка вида и подрезка аннотаций "
    u"(с минимальным отступом от рамки), копия открывается. Работает на "
    u"планах, разрезах, фасадах и узлах. Esc — отмена."
)
__author__ = "Pipers"

import traceback

from Autodesk.Revit.DB import Element, Transaction
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import PickBoxStyle
from pyrevit import revit, forms, script

from lowlife import view_crop, view_crop_dialog

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

TITLE = u"Обрезать вид"


reason = view_crop.unsupported_reason(view)
if reason:
    forms.alert(reason, title=TITLE, exitscript=True)

# Рамка — PickBox: два клика (или протяжка) с живым прямоугольником. В
# отличие от двух PickPoint не ищет привязки на каждое движение мыши (в
# тяжёлых видах/связях Revit на этом подвисал), не требует рабочей плоскости
# и идёт без открытых транзакций.
try:
    box = uidoc.Selection.PickBox(
        PickBoxStyle.Enclosing,
        u"Обрезать вид: укажите два противоположных угла рамки")
except OperationCanceledException:
    script.exit()
pt1, pt2 = box.Min, box.Max

try:
    view_crop.check_points(view, pt1, pt2)
except ValueError as err:
    forms.alert(unicode(err), title=TITLE, exitscript=True)

choice = view_crop_dialog.ask(view_crop.available_modes(view), Element.Name.GetValue(view))
if choice is None:
    script.exit()
mode, suffix = choice

t = Transaction(doc, TITLE)
t.Start()
try:
    target = view_crop.duplicate_view(doc, view, mode, suffix)
    warnings = view_crop.apply_crop(target, pt1, pt2)
    t.Commit()
except Exception:
    t.RollBack()
    forms.alert(u"Не удалось обрезать вид (возможно, подрезка задана "
                u"шаблоном вида).\n\n" + traceback.format_exc(),
                title=TITLE, exitscript=True)

if target.Id != view.Id:
    uidoc.ActiveView = target
if warnings:
    forms.alert(u"\n".join(warnings), title=TITLE)
